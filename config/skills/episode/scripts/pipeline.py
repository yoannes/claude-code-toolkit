#!/usr/bin/env python3
"""
Episode Pipeline - Media generation orchestrator for /episode skill.

Generates educational video episodes by orchestrating:
- Flux (fal.ai) for keyframe images
- Kling I2V (fal.ai) for video clips
- ElevenLabs for TTS audio
- FFmpeg for final assembly

Usage:
    python pipeline.py <manifest.json> [--phase images|clips|audio|assemble|all]

The script is resumable - it reads the manifest and skips completed work.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import shutil
from pathlib import Path

# Check for required packages
try:
    import fal_client
except ImportError:
    print("ERROR: fal-client not installed. Run: pip install fal-client", file=sys.stderr)
    sys.exit(1)

try:
    from elevenlabs import ElevenLabs
except ImportError:
    print("ERROR: elevenlabs not installed. Run: pip install elevenlabs", file=sys.stderr)
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================

FAL_FLUX_MODEL = "fal-ai/flux/dev"
FAL_KLING_MODEL = "fal-ai/kling-video/v2.1/pro/image-to-video"
ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George - good narrator voice
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Costs (approximate, for tracking)
COST_FLUX_IMAGE = 0.05  # per image
COST_KLING_VIDEO_PER_SEC = 0.07  # per second of video
COST_ELEVENLABS_PER_CHAR = 0.00003  # per character

# Polling configuration
POLL_INTERVAL_INITIAL = 5  # seconds
POLL_INTERVAL_MAX = 60  # seconds
POLL_BACKOFF_FACTOR = 1.5
MAX_POLL_TIME = 600  # 10 minutes max per operation

# Concurrency limits
MAX_CONCURRENT_VIDEOS = 3


# =============================================================================
# Manifest Operations
# =============================================================================


def load_manifest(path: str) -> dict:
    """Load manifest from JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def save_manifest(path: str, manifest: dict) -> None:
    """Save manifest to JSON file atomically."""
    temp_path = path + ".tmp"
    with open(temp_path, "w") as f:
        json.dump(manifest, f, indent=2)
    shutil.move(temp_path, path)


def get_episode_dir(manifest_path: str) -> Path:
    """Get the episode directory from manifest path."""
    return Path(manifest_path).parent


def ensure_dirs(episode_dir: Path) -> None:
    """Ensure asset directories exist."""
    (episode_dir / "assets" / "images").mkdir(parents=True, exist_ok=True)
    (episode_dir / "assets" / "clips").mkdir(parents=True, exist_ok=True)
    (episode_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)


# =============================================================================
# fal.ai Operations
# =============================================================================


def generate_image(scene: dict, episode_dir: Path) -> dict:
    """Generate keyframe image via Flux."""
    scene_id = scene["scene_id"]
    prompt = scene["visual_prompt"]

    print(f"  [{scene_id}] Generating image...")

    try:
        result = fal_client.subscribe(
            FAL_FLUX_MODEL,
            arguments={
                "prompt": prompt,
                "image_size": "landscape_16_9",
                "num_images": 1,
            },
        )

        # Download image
        image_url = result["images"][0]["url"]
        image_path = episode_dir / "assets" / "images" / f"{scene_id}.png"

        # Use fal_client to download
        import urllib.request
        urllib.request.urlretrieve(image_url, str(image_path))

        print(f"  [{scene_id}] Image saved: {image_path}")

        return {
            "status": "completed",
            "fal_request_id": None,  # subscribe is synchronous
            "asset_path": str(image_path),
            "cost_usd": COST_FLUX_IMAGE,
        }

    except Exception as e:
        print(f"  [{scene_id}] Image generation failed: {e}", file=sys.stderr)
        return {
            "status": "failed",
            "fal_request_id": None,
            "asset_path": None,
            "cost_usd": 0,
            "error": str(e),
        }


def submit_video(scene: dict, episode_dir: Path) -> dict:
    """Submit video generation job to Kling queue."""
    scene_id = scene["scene_id"]
    image_path = scene["image"]["asset_path"]
    prompt = scene["visual_prompt"]
    # Note: Kling max is 10s, we always generate 10s and trim later if needed

    print(f"  [{scene_id}] Submitting video job...")

    try:
        # Read image and convert to base64 data URL
        import base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        image_url = f"data:image/png;base64,{image_data}"

        # Submit to queue
        handler = fal_client.submit(
            FAL_KLING_MODEL,
            arguments={
                "prompt": prompt,
                "image_url": image_url,
                "duration": "10",  # Always generate 10s, trim later if needed
                "aspect_ratio": "16:9",
            },
        )

        request_id = handler.request_id
        print(f"  [{scene_id}] Video job submitted: {request_id}")

        return {
            "status": "submitted",
            "fal_request_id": request_id,
            "asset_path": None,
            "cost_usd": 0,
        }

    except Exception as e:
        print(f"  [{scene_id}] Video submission failed: {e}", file=sys.stderr)
        return {
            "status": "failed",
            "fal_request_id": None,
            "asset_path": None,
            "cost_usd": 0,
            "error": str(e),
        }


def poll_video(scene: dict, episode_dir: Path) -> dict:
    """Poll for video completion and download."""
    scene_id = scene["scene_id"]
    request_id = scene["clip"]["fal_request_id"]

    if not request_id:
        return scene["clip"]

    print(f"  [{scene_id}] Polling video job {request_id}...")

    try:
        # Check status
        status = fal_client.status(FAL_KLING_MODEL, request_id, with_logs=False)

        if hasattr(status, "status"):
            status_str = status.status
        else:
            status_str = str(status)

        if "COMPLETED" in status_str.upper() or "completed" in str(status).lower():
            # Get result
            result = fal_client.result(FAL_KLING_MODEL, request_id)
            video_url = result["video"]["url"]

            # Download video
            video_path = episode_dir / "assets" / "clips" / f"{scene_id}.mp4"
            import urllib.request
            urllib.request.urlretrieve(video_url, str(video_path))

            duration = 10  # Assume 10s
            cost = duration * COST_KLING_VIDEO_PER_SEC

            print(f"  [{scene_id}] Video saved: {video_path}")

            return {
                "status": "completed",
                "fal_request_id": request_id,
                "asset_path": str(video_path),
                "cost_usd": cost,
            }

        elif "FAILED" in status_str.upper() or "failed" in str(status).lower():
            return {
                "status": "failed",
                "fal_request_id": request_id,
                "asset_path": None,
                "cost_usd": 0,
                "error": "Video generation failed on fal.ai",
            }

        else:
            # Still in progress
            print(f"  [{scene_id}] Video still processing: {status_str}")
            return scene["clip"]  # Return unchanged

    except Exception as e:
        print(f"  [{scene_id}] Polling failed: {e}", file=sys.stderr)
        return scene["clip"]  # Return unchanged, will retry


# =============================================================================
# ElevenLabs Operations
# =============================================================================


def generate_audio(scene: dict, episode_dir: Path) -> dict:
    """Generate TTS audio via ElevenLabs."""
    scene_id = scene["scene_id"]
    narration = scene["narration"]

    print(f"  [{scene_id}] Generating audio...")

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return {
            "status": "failed",
            "asset_path": None,
            "cost_usd": 0,
            "error": "ELEVENLABS_API_KEY not set",
        }

    try:
        client = ElevenLabs(api_key=api_key)

        audio_generator = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=narration,
            model_id=ELEVENLABS_MODEL,
            output_format="mp3_44100_128",
        )

        # Save audio
        audio_path = episode_dir / "assets" / "audio" / f"{scene_id}.mp3"
        with open(audio_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)

        cost = len(narration) * COST_ELEVENLABS_PER_CHAR

        print(f"  [{scene_id}] Audio saved: {audio_path}")

        return {
            "status": "completed",
            "asset_path": str(audio_path),
            "cost_usd": cost,
        }

    except Exception as e:
        print(f"  [{scene_id}] Audio generation failed: {e}", file=sys.stderr)
        return {
            "status": "failed",
            "asset_path": None,
            "cost_usd": 0,
            "error": str(e),
        }


# =============================================================================
# FFmpeg Assembly
# =============================================================================


def assemble_episode(manifest: dict, episode_dir: Path) -> dict:
    """Assemble final video from clips and audio."""
    print("Assembling final episode...")

    scenes = manifest["scenes"]

    # Check all clips and audio are ready
    for scene in scenes:
        if scene["clip"]["status"] != "completed":
            return {"status": "blocked", "asset_path": None, "error": f"Clip {scene['scene_id']} not ready"}
        if scene["audio"]["status"] != "completed":
            return {"status": "blocked", "asset_path": None, "error": f"Audio {scene['scene_id']} not ready"}

    try:
        # Create concat file for videos
        concat_file = episode_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for scene in scenes:
                clip_path = Path(scene["clip"]["asset_path"]).resolve()
                f.write(f"file '{clip_path}'\n")

        # Concatenate videos (simple concat, no crossfade for simplicity)
        video_only = episode_dir / "video_only.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(video_only),
        ], check=True, capture_output=True)

        # Concatenate audio files
        audio_concat = episode_dir / "audio_concat.txt"
        with open(audio_concat, "w") as f:
            for scene in scenes:
                audio_path = Path(scene["audio"]["asset_path"]).resolve()
                f.write(f"file '{audio_path}'\n")

        audio_only = episode_dir / "audio_only.mp3"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(audio_concat),
            "-c", "copy",
            str(audio_only),
        ], check=True, capture_output=True)

        # Merge video and audio
        final_path = episode_dir / "episode.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_only),
            "-i", str(audio_only),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(final_path),
        ], check=True, capture_output=True)

        # Cleanup temp files
        concat_file.unlink(missing_ok=True)
        audio_concat.unlink(missing_ok=True)
        video_only.unlink(missing_ok=True)
        audio_only.unlink(missing_ok=True)

        print(f"Final episode saved: {final_path}")

        return {
            "status": "completed",
            "asset_path": str(final_path),
        }

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        print(f"FFmpeg assembly failed: {error_msg}", file=sys.stderr)
        return {
            "status": "failed",
            "asset_path": None,
            "error": error_msg,
        }
    except Exception as e:
        print(f"Assembly failed: {e}", file=sys.stderr)
        return {
            "status": "failed",
            "asset_path": None,
            "error": str(e),
        }


# =============================================================================
# Phase Runners
# =============================================================================


def run_images_phase(manifest: dict, manifest_path: str, episode_dir: Path) -> None:
    """Generate all keyframe images."""
    print("\n=== Phase: Images ===")

    for scene in manifest["scenes"]:
        if scene["image"]["status"] == "completed":
            print(f"  [{scene['scene_id']}] Image already complete, skipping")
            continue

        result = generate_image(scene, episode_dir)
        scene["image"].update(result)
        manifest["cost_spent_usd"] += result.get("cost_usd", 0)
        save_manifest(manifest_path, manifest)

    # Summary
    completed = sum(1 for s in manifest["scenes"] if s["image"]["status"] == "completed")
    total = len(manifest["scenes"])
    print(f"\nImages: {completed}/{total} completed")


def run_clips_phase(manifest: dict, manifest_path: str, episode_dir: Path) -> None:
    """Generate all video clips via queue-based processing."""
    print("\n=== Phase: Video Clips ===")

    # First, submit all pending jobs
    pending_count = 0
    for scene in manifest["scenes"]:
        if scene["clip"]["status"] in ["completed", "submitted"]:
            continue
        if scene["image"]["status"] != "completed":
            print(f"  [{scene['scene_id']}] Image not ready, skipping clip")
            continue

        result = submit_video(scene, episode_dir)
        scene["clip"].update(result)
        save_manifest(manifest_path, manifest)
        pending_count += 1

        # Rate limit: max concurrent submissions
        if pending_count >= MAX_CONCURRENT_VIDEOS:
            print(f"  Reached concurrent limit ({MAX_CONCURRENT_VIDEOS}), waiting...")
            time.sleep(10)
            pending_count = 0

    # Poll for completion
    print("\nPolling for video completion...")
    poll_interval = POLL_INTERVAL_INITIAL
    start_time = time.time()

    while True:
        # Check if all done or failed
        submitted = [s for s in manifest["scenes"] if s["clip"]["status"] == "submitted"]
        if not submitted:
            break

        # Check timeout
        if time.time() - start_time > MAX_POLL_TIME:
            print(f"Polling timeout after {MAX_POLL_TIME}s. Re-run to continue.")
            break

        # Poll each submitted job
        for scene in submitted:
            result = poll_video(scene, episode_dir)
            if result["status"] != scene["clip"]["status"]:
                scene["clip"].update(result)
                manifest["cost_spent_usd"] += result.get("cost_usd", 0)
                save_manifest(manifest_path, manifest)

        # Wait before next poll
        remaining = sum(1 for s in manifest["scenes"] if s["clip"]["status"] == "submitted")
        if remaining > 0:
            print(f"  {remaining} videos still processing, waiting {poll_interval}s...")
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * POLL_BACKOFF_FACTOR, POLL_INTERVAL_MAX)

    # Summary
    completed = sum(1 for s in manifest["scenes"] if s["clip"]["status"] == "completed")
    total = len(manifest["scenes"])
    print(f"\nClips: {completed}/{total} completed")


def run_audio_phase(manifest: dict, manifest_path: str, episode_dir: Path) -> None:
    """Generate all TTS audio."""
    print("\n=== Phase: Audio ===")

    for scene in manifest["scenes"]:
        if scene["audio"]["status"] == "completed":
            print(f"  [{scene['scene_id']}] Audio already complete, skipping")
            continue

        result = generate_audio(scene, episode_dir)
        scene["audio"].update(result)
        manifest["cost_spent_usd"] += result.get("cost_usd", 0)
        save_manifest(manifest_path, manifest)

    # Summary
    completed = sum(1 for s in manifest["scenes"] if s["audio"]["status"] == "completed")
    total = len(manifest["scenes"])
    print(f"\nAudio: {completed}/{total} completed")


def run_assemble_phase(manifest: dict, manifest_path: str, episode_dir: Path) -> None:
    """Assemble final episode."""
    print("\n=== Phase: Assembly ===")

    if manifest["assembly"]["status"] == "completed":
        print("Assembly already complete, skipping")
        return

    result = assemble_episode(manifest, episode_dir)
    manifest["assembly"].update(result)
    save_manifest(manifest_path, manifest)

    if result["status"] == "completed":
        print(f"\n✓ Episode complete: {result['asset_path']}")
        print(f"  Total cost: ${manifest['cost_spent_usd']:.2f}")


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Episode pipeline orchestrator")
    parser.add_argument("manifest", help="Path to manifest.json")
    parser.add_argument(
        "--phase",
        choices=["images", "clips", "audio", "assemble", "all"],
        default="all",
        help="Run specific phase only",
    )
    args = parser.parse_args()

    # Check API keys
    if not os.environ.get("FAL_KEY"):
        print("ERROR: FAL_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("ELEVENLABS_API_KEY"):
        print("ERROR: ELEVENLABS_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Load manifest
    manifest_path = args.manifest
    if not Path(manifest_path).exists():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    manifest = load_manifest(manifest_path)
    episode_dir = get_episode_dir(manifest_path)
    ensure_dirs(episode_dir)

    print(f"Episode: {manifest.get('title', 'Untitled')}")
    print(f"Scenes: {len(manifest['scenes'])}")
    print(f"Budget: ${manifest.get('cost_budget_usd', 0):.2f}")
    print(f"Spent: ${manifest.get('cost_spent_usd', 0):.2f}")

    # Run phases
    if args.phase in ["images", "all"]:
        run_images_phase(manifest, manifest_path, episode_dir)

    if args.phase in ["clips", "all"]:
        run_clips_phase(manifest, manifest_path, episode_dir)

    if args.phase in ["audio", "all"]:
        run_audio_phase(manifest, manifest_path, episode_dir)

    if args.phase in ["assemble", "all"]:
        run_assemble_phase(manifest, manifest_path, episode_dir)

    # Final status
    print("\n=== Final Status ===")
    print(f"Cost spent: ${manifest['cost_spent_usd']:.2f}")

    images_done = sum(1 for s in manifest["scenes"] if s["image"]["status"] == "completed")
    clips_done = sum(1 for s in manifest["scenes"] if s["clip"]["status"] == "completed")
    audio_done = sum(1 for s in manifest["scenes"] if s["audio"]["status"] == "completed")
    total = len(manifest["scenes"])

    print(f"Images: {images_done}/{total}")
    print(f"Clips: {clips_done}/{total}")
    print(f"Audio: {audio_done}/{total}")
    print(f"Assembly: {manifest['assembly']['status']}")

    if manifest["assembly"]["status"] == "completed":
        print(f"\n✓ Episode ready: {manifest['assembly']['asset_path']}")
        sys.exit(0)
    else:
        print("\n⚠ Episode not complete. Re-run to continue.")
        sys.exit(1)


if __name__ == "__main__":
    main()
