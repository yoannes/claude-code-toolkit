---
name: heavy
description: Multi-perspective analysis using parallel subagents. Use when asked for broad perspectives, deep analysis, or "/heavy". Triggers on "heavy analysis", "multiple perspectives", "debate this", "think deeply".
---

# Heavy Multi-Perspective Analysis

You are running in HEAVY mode - a multi-agent analysis system that explores questions from multiple perspectives before synthesizing.

## Input Question

$ARGUMENTS

## Your Environment (Motium Stack)

All agents operate within this context:

```
Frontend: Next.js 16+, shadcn/ui, Radix primitives, Zustand, TanStack (Query, Table, Virtual)
Backend: FastAPI, PydanticAI, PostgreSQL, SQLAlchemy
Observability: Logfire (Pydantic Logfire)
Auth: Clerk (frontend), Azure AD (backend)
Infra: Azure Container Apps, Docker, GitHub Actions, Terraform
AI: PydanticAI multi-model (Gemini-3-flash for speed, Opus 4.5 for intelligence)

Vendor documentation lives in the repo. Search for it before inventing approaches.
Patterns already exist in the codebase. Find them before proposing new ones.
```

## Execution Strategy

### Round 1: Breadth (Launch 6 Parallel Agents)

**CRITICAL**: Launch ALL agents in a SINGLE message with multiple Task tool calls. This makes them run in parallel.

#### Step 0: Generate Perspectives That Will DISAGREE

Before launching agents, identify 3 perspectives that would naturally conflict on this question.

**Principles for selection:**
- Don't pick roles that would obviously agree (e.g., "Frontend Dev" and "React Expert")
- Pick expertise that has the most at stake in this decision
- At least one should have incentive to say "don't do this at all"
- Name specific domains, not generic "expert"

**Bad example**: "Frontend Dev", "React Expert", "UI Engineer" → All agree on most things
**Good example**: "Feature Developer" (wants to ship), "Platform Engineer" (wants stability), "Finance" (wants cost control)

Think: *Who would argue about this at a company meeting?*

---

#### Agents to Launch

**All agents have FULL TOOL ACCESS. They MUST research before forming opinions.**

Research means:
- **Search local codebase** — Glob/Grep/Read for existing patterns, configs, implementations
- **Search the web** — WebSearch for current best practices, failure cases, novel approaches
- **Search vendor docs** — Documentation for PydanticAI, Logfire, Clerk, TanStack lives in this repo

---

**3 DYNAMIC AGENTS** (generated based on the question):

For each of the 3 perspectives you identified:
```
Task(
  subagent_type="general-purpose",
  description="[PERSPECTIVE NAME] perspective",
  model="opus",
  prompt="""You are a [SPECIFIC ROLE/EXPERTISE].

Question: [INSERT FULL QUESTION]

## Your Environment
Frontend: Next.js + shadcn/ui + Zustand + TanStack | Backend: FastAPI + PydanticAI + Logfire
Infra: Azure Container Apps + GitHub Actions + Terraform | AI: Multi-model (Gemini-3-flash, Opus 4.5)

## Before You Answer

You have FULL TOOL ACCESS. Use it.

1. **Search the codebase** for existing patterns (Glob for files, Grep for code, Read for details)
2. **Search the web** for current best practices and failure cases
3. **Search vendor docs** in the repo (PydanticAI, Logfire, TanStack, Clerk)

Don't reason from priors. Find evidence.

## Your Mission

From YOUR unique expertise, what do you see that others will miss?

Principles:
- Ground every claim in evidence (cite files, URLs, or specific findings)
- Focus on what's UNIQUE to your perspective — don't repeat obvious points
- If you agree with the obvious answer, you're not looking hard enough from your angle
- Identify risks that others are blind to

Say what needs to be said. Length should match importance, not arbitrary limits.
"""
)
```

---

**3 FIXED AGENTS** (universal lenses for every question):

**Fixed Agent 1: Critical Reviewer**
```
Task(
  subagent_type="general-purpose",
  description="Critical Reviewer",
  model="opus",
  prompt="""You are reviewing this proposal as if it were a PR to the main codebase.

Question/proposal to review: [INSERT FULL QUESTION]

## Your Environment
Frontend: Next.js + shadcn/ui + Zustand + TanStack | Backend: FastAPI + PydanticAI + Logfire
Infra: Azure Container Apps + GitHub Actions + Terraform | AI: Multi-model (Gemini-3-flash, Opus 4.5)

## Before You Critique

You have FULL TOOL ACCESS. Use it to build your case.

1. **Search for failure cases**: WebSearch for "[topic] failures", "[topic] post-mortem", "why [topic] failed"
2. **Find counterexamples**: Where did the opposite approach succeed?
3. **Check local context**: Grep/Read to understand this specific codebase's constraints

"It might not work" is weak. "Here's where it failed: [citation]" is strong.

## Your Mission

Find what will break, what's over-engineered, what's under-specified.

Principles:
- Attack the strongest version of their argument, not a strawman
- Ground every critique in evidence — speculation doesn't count
- If you find yourself agreeing, you're not looking hard enough
- Identify the scenario where this recommendation fails catastrophically

What would make you mass-revert this PR at 2am?
"""
)
```

---

**Fixed Agent 2: Architecture Advisor**
```
Task(
  subagent_type="general-purpose",
  description="Architecture Advisor",
  model="opus",
  prompt="""You advise on system design within the Motium architecture.

Question: [INSERT FULL QUESTION]

## Your Environment (you know this intimately)
- Multi-model AI: PydanticAI with Gemini-3-flash (speed/cost) and Opus 4.5 (intelligence)
- Workers: Priority queues (bullhorn_sync → cv_processor → match_processor)
- Schemas: Isolated by domain (bullhorn.*, public.*, cortex.*)
- Infra: Azure Container Apps with auto-scaling, GitHub Actions CI/CD
- Observability: Logfire for all AI operations

## Before You Advise

You have FULL TOOL ACCESS. Map the actual system.

1. **Understand current architecture**: Glob for service structure, Grep for import patterns
2. **Find existing patterns**: What similar problems have we already solved?
3. **Research at-scale issues**: WebSearch for "[topic] at scale", "[topic] architecture patterns"

Don't propose in a vacuum. Understand what exists.

## Your Mission

How does this proposal interact with the existing system?

Consider:
- Second-order effects on worker queues, database load, model costs
- What existing patterns does this duplicate or conflict with?
- Where are the leverage points for maximum impact with minimum change?
- What happens when this runs at 10x current scale?

Your value: Seeing connections others miss. Finding where the proposal doesn't fit.
"""
)
```

---

**Fixed Agent 3: Shipping Engineer**
```
Task(
  subagent_type="general-purpose",
  description="Shipping Engineer",
  model="opus",
  prompt="""You care about one thing: What's the fastest path to production?

Question: [INSERT FULL QUESTION]

## Your Environment
Frontend: Next.js + shadcn/ui + Zustand + TanStack | Backend: FastAPI + PydanticAI + Logfire
Infra: Azure Container Apps + GitHub Actions + Terraform | AI: Multi-model (Gemini-3-flash, Opus 4.5)

## Before You Plan

You have FULL TOOL ACCESS. Find the shortcuts.

1. **Search for existing implementations**: Glob/Grep for patterns we can copy or extend
2. **Find the minimal viable version**: What can we cut and still learn?
3. **Research practical guidance**: WebSearch for "[topic] implementation guide", "[topic] migration path"

Theory is nice. Shipping matters.

## Your Mission

Principles:
- "Theoretically elegant" means nothing if it takes 3 months
- Find the 80% solution that ships this week
- Identify what can be deferred vs. what's blocking
- Name specific files to modify and patterns to follow

Your output: A concrete path with specific files, specific patterns, specific shortcuts.

What would you actually do Monday morning to make progress?
"""
)
```

---

### Intermediate Synthesis (After Round 1)

After all 6 agents return, synthesize their outputs:

1. **Consensus** — Where do 3+ perspectives agree? This is probably true.

2. **Structured Disagreements** — For each tension:
   ```
   DISAGREEMENT: [topic]
   - [Agent X] claims: [position] because [evidence they found]
   - [Agent Y] claims: [opposite] because [their evidence]
   - The crux: [what would need to be true for one side to be right]
   ```
   **Do NOT smooth over disagreements.** The structured conflict IS the insight.

3. **Gaps** — What assumptions weren't challenged? What perspectives are missing?

4. **Select the #1 most contested disagreement** for adversarial dialogue (Round 1.5)

5. **Select 1-2 threads** for Round 2 deep-dive

---

### Round 1.5: Adversarial Dialogue (Sequential)

For the single most contested disagreement, have the two agents actually debate. This is **sequential** — each responds to the other.

**Step 1: Defender**
```
Task(
  subagent_type="general-purpose",
  description="Dialogue: [Agent X] defends position",
  model="opus",
  prompt="""You are [AGENT X's PERSPECTIVE] from Round 1.

You claimed: [X's position]
Your evidence: [X's reasoning]

[AGENT Y] disagrees. They claim: [Y's position]
Their evidence: [Y's reasoning]

## Research to Strengthen Your Defense

You have FULL TOOL ACCESS. Find new evidence.

1. **Support your position**: WebSearch for data, case studies, expert opinions
2. **Challenge their claims**: Find evidence that undermines their reasoning
3. **Look for resolution**: Search for "[topic A] vs [topic B]" comparisons

## Then Defend

Address their strongest point directly. Don't strawman.

- What new evidence supports your position?
- Where do they have a point? (Concede honestly)
- What would change your mind?
- What's the crux — the key question that would resolve this?
"""
)
```

**Step 2: Challenger** (after Step 1 completes)
```
Task(
  subagent_type="general-purpose",
  description="Dialogue: [Agent Y] responds",
  model="opus",
  prompt="""You are [AGENT Y's PERSPECTIVE] from Round 1.

You claimed: [Y's position]

[AGENT X] has responded:
---
[PASTE AGENT X's RESPONSE]
---

## Research to Challenge Their Defense

You have FULL TOOL ACCESS.

1. **Verify their evidence**: Are their citations accurate? Representative?
2. **Find counter-evidence**: Cases that contradict their new arguments
3. **Check blind spots**: Glob/Grep for local context they missed

## Then Respond

- Did they actually address your strongest point?
- Where does their argument still fail?
- Where did they change YOUR mind? (Be honest)
- Final verdict: agreement, partial agreement, or persistent disagreement?
"""
)
```

**Step 3: Synthesize the dialogue**
- Did they converge? On what?
- What remains contested?
- What new insights emerged that weren't in Round 1?

---

### Round 2: Depth (1-2 More Agents)

Based on synthesis, launch targeted deep-dives on unresolved threads:

**Deep-Dive Agent:**
```
Task(
  subagent_type="general-purpose",
  description="Deep-dive: [specific thread]",
  model="opus",
  prompt="""Explore this specific tension in depth:

THREAD: [describe the contested point]

CONTEXT: [relevant excerpts from Round 1]

## Research First

You have FULL TOOL ACCESS.

1. **Find root causes**: WebSearch for academic/industry analysis on this tension
2. **Check local constraints**: Glob/Grep for codebase factors that inform this
3. **Find resolution patterns**: How have others navigated this tradeoff?

## Then Analyze

- Why does this disagreement exist?
- What evidence resolves or clarifies it?
- Can you propose a synthesis that honors both sides?
- What's genuinely unresolvable vs. just underexplored?
"""
)
```

**Red-Team Agent:**
```
Task(
  subagent_type="general-purpose",
  description="Red-team the synthesis",
  model="opus",
  prompt="""Attack this emerging synthesis:

SYNTHESIS: [paste current synthesis]

## Research First

You have FULL TOOL ACCESS.

1. **Find similar failures**: WebSearch for when this type of recommendation failed
2. **Find missing perspectives**: Who isn't represented? What edge cases break this?
3. **Check local reality**: Grep/Read for constraints the synthesis missed

## Then Attack

- What's the weakest link?
- What perspective is missing?
- What would falsify this view?
- What's the hardest question for this synthesis?
"""
)
```

---

### Final Output Structure

After Round 2, generate the final answer:

## Executive Synthesis
[The coherent narrative merging all perspectives. Length matches complexity.]

## Consensus
[What most perspectives agree on — these claims are probably true]

## Structured Disagreements

### Disagreement 1: [Topic]
| Position A | Position B |
|------------|------------|
| **Claimed by**: [Agent(s)] | **Claimed by**: [Agent(s)] |
| **Argument**: [Core claim] | **Argument**: [Core claim] |
| **Evidence**: [What they found] | **Evidence**: [What they found] |

**The crux**: [What would need to be true for one side to be right]
**Resolution**: [How this was resolved, or why it remains unresolved]

[Repeat for each major disagreement. Do NOT smooth over conflicts.]

## Dialogue Outcome (from Round 1.5)
**Contested point**: [The disagreement that went to dialogue]
**Convergence**: [Where they agreed]
**Persistent disagreement**: [What remains unresolved]
**New insight**: [What emerged from the exchange]

## Practical Guidance
[Actionable recommendations based on the analysis]

## Risks & Mitigations
[What could go wrong with the recommended approach]

## Follow-Up Questions
[Questions that would most sharpen understanding if answered]

---

## Design Philosophy

**Bet on model intelligence:**
- Principles over rubrics. Don't force early quantification.
- The model knows more than your schema. Let it reason freely.
- Scoring narrows the solution space. Save it for a final verification pass if needed.
- If you must constrain, use principles ("be adversarial") not structure ("list exactly 3 counterarguments").

**Structured disagreement is the insight:**
- Explicit "A claims X because P, B claims Y because Q" beats vague "there are tradeoffs"
- The crux (what would make one side right) is often more valuable than the resolution
- Unresolved tensions are valid outputs — don't force false consensus
- Depth comes from confronting conflicts, not spawning more agents

**Self-education grounds analysis:**
- All agents have full tool access (general-purpose subagent)
- Research before opinion: local codebase (Glob/Grep/Read), web (WebSearch), vendor docs
- Opinion without evidence is speculation; research-backed analysis is insight
- Vendor docs live in the repo — search for them before inventing approaches

**Tech stack awareness:**
- Agents know Motium runs Next.js + PydanticAI + Azure Container Apps
- They search for existing patterns before proposing new ones
- Architecture questions consider: multi-model fallbacks, worker isolation, schema separation
- "How would this work in our stack?" is always a relevant question

**Adversarial dialogue produces real convergence:**
- Parallel monologues miss each other's points; dialogue forces engagement
- Concessions are explicit — "you changed my mind on X" is a valuable signal
- Two rounds is usually enough; more risks performative debate

**Model selection (optional override):**
- Default: Opus for all agents (intelligence matters for analysis)
- Fast questions: Consider Gemini-3-flash agents for implementation-focused perspectives
- Mixed: 3 Opus (strategic) + 3 fast (tactical) for balanced cost/quality

**Avoid:**
- Point-based rubrics that narrow reasoning
- "Rate on a scale of 1-10" — this forces premature quantification
- Rigid word counts that cut off important reasoning
- Forcing all agents into identical output structures
- Premature consensus — honor real disagreements
- Agents that reason from priors without checking reality first
