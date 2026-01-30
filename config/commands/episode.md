---
description: Generate educational video episodes with Minecraft-style graphics
argument-hint: <topic> [--duration 3|10]
---

# /episode

Generate educational video episodes with Minecraft-style graphics.

## Arguments

- `<topic>` - The educational topic to explain (required)
- `--duration 3|10` - Episode duration in minutes (default: 3)

## Examples

```
/episode "How photosynthesis works"
/episode "Introduction to fractions" --duration 10
/episode "The water cycle"
```

## Instructions

1. **Read the episode skill** to understand the workflow:
   @~/.claude/skills/episode/SKILL.md

2. **Write the episode script** as a JSON manifest following the 7-act structure

3. **Run the pipeline** to generate media:
   ```bash
   python3 ~/.claude/skills/episode/scripts/pipeline.py episodes/EP001/manifest.json
   ```

4. **Review the output** at `episodes/EP001/episode.mp4`
