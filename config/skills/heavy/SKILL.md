---
name: heavy
description: Multi-perspective analysis using parallel subagents. Use when asked for broad perspectives, deep analysis, or "/heavy". Triggers on "heavy analysis", "multiple perspectives", "debate this", "think deeply".
---

# Heavy Multi-Perspective Analysis

You are running in HEAVY mode - a multi-agent analysis system that explores questions from multiple perspectives before synthesizing.

## Input Question

$ARGUMENTS

## Execution Strategy

### Round 1: Breadth (Launch 6 Parallel Agents)

**CRITICAL**: Launch ALL agents in a SINGLE message with multiple Task tool calls. This makes them run in parallel.

#### Step 0: Generate Dynamic Lenses

Before launching agents, analyze the question and generate 3 domain-relevant perspectives. Think:

```
Question: [USER'S QUESTION]

What are the 3 most relevant expert perspectives for THIS specific question?
- Not generic "domain expert" — name the specific domain
- Not "prompt engineering" unless the question is actually about prompts
- Consider: the industry, the technical domain, stakeholders affected, methodologies involved

Examples:
- "Should we use microservices?" → Software Architect, DevOps Engineer, Team Lead
- "How should we price our product?" → Pricing Strategist, Customer Researcher, Finance Analyst
- "Should we use RAG or fine-tuning?" → ML Engineer, Prompt Engineer, Infrastructure Lead
- "How do we improve retention?" → Product Manager, Data Analyst, UX Researcher
```

#### Agents to Launch

**3 DYNAMIC AGENTS** (generated based on the question):

For each of the 3 domain-relevant perspectives you identified:
```
Task(
  subagent_type="general-purpose",
  description="[PERSPECTIVE NAME] perspective",
  model="opus",
  prompt="""You are a [SPECIFIC ROLE/EXPERTISE].

Question: [INSERT FULL QUESTION]

Analyze this from your specific expertise. Focus on what YOU uniquely see that other perspectives might miss.

Deliver (max 300 words):
1. **Key insights from your perspective** (max 6 bullets)
2. **What others might overlook** (2-3 points)
3. **Risks you're uniquely positioned to see** (2-3)
4. **Follow-up questions** (3)
"""
)
```

---

**3 FIXED AGENTS** (universal lenses that apply to any question):

**Fixed Agent 1: Contrarian**
```
Task(
  subagent_type="general-purpose",
  description="Contrarian perspective",
  model="opus",
  prompt="""You are a rigorous contrarian. Your job is to find weaknesses in whatever is being proposed or considered.

Question/proposal to stress-test: [INSERT FULL QUESTION]

Deliver (max 250 words):
1. **Strongest counterargument**
2. **Where this approach breaks** in practice (2-3 scenarios)
3. **What evidence would change your mind**
4. **"Gotcha" questions** (3)

Be constructive but relentless. Don't strawman.
"""
)
```

---

**Fixed Agent 2: Systems Thinker**
```
Task(
  subagent_type="general-purpose",
  description="Systems perspective",
  model="opus",
  prompt="""You are a systems thinker. Analyze the second and third-order effects.

Question: [INSERT FULL QUESTION]

Deliver (max 300 words):
1. **System boundaries** - what's in/out scope
2. **Feedback loops** - reinforcing and balancing
3. **Emergent behaviors** - what happens at scale
4. **Leverage points** - where small changes have big effects
5. **Follow-up questions** (3)
"""
)
```

---

**Fixed Agent 3: Pragmatist**
```
Task(
  subagent_type="general-purpose",
  description="Pragmatist perspective",
  model="opus",
  prompt="""You are a pragmatic implementer. Theory is nice, shipping matters.

Question: [INSERT FULL QUESTION]

Deliver (max 250 words):
1. **Implementation path** - simplest viable approach
2. **Gotchas** - what breaks when you actually build this
3. **Iteration strategy** - how to start small and learn
4. **Follow-up questions** (3)
"""
)
```

---

### Intermediate Synthesis (After Round 1)

After all 6 agents return, synthesize their outputs:

1. **Consensus points** - Where do 3+ perspectives agree?
2. **Structured Disagreements** - For each tension, explicitly surface:
   ```
   DISAGREEMENT: [topic]
   - Agent [X] claims: [position P] because [reasoning A]
   - Agent [Y] claims: [position Q] because [reasoning B]
   - The crux: [what would need to be true for one side to be right]
   - Resolution path: [what evidence/analysis would resolve this]
   ```
   Do NOT smooth over disagreements. The structured conflict IS the insight.
3. **Gaps** - What's missing? What assumptions weren't challenged?
4. **Select the #1 most contested disagreement** for adversarial dialogue (Round 1.5)
5. **Select 1-2 additional threads** for Round 2 deep-dive

---

### Round 1.5: Adversarial Dialogue (Sequential, on #1 Disagreement)

For the single most contested disagreement, have the two disagreeing agents actually converse. This is **sequential** (not parallel) - each agent responds to the other's output.

**Step 1: Defender states position**
```
Task(
  subagent_type="general-purpose",
  description="Dialogue: [Agent X] defends position",
  model="opus",
  prompt="""You are [AGENT X's LENS] from Round 1.

You claimed: [X's position from Round 1]
Your reasoning was: [X's reasoning]

[AGENT Y] disagrees. They claim: [Y's position]
Their reasoning: [Y's reasoning]

Your task: DEFEND your position against their critique.
- Address their strongest point directly
- Provide additional evidence or reasoning
- Identify where you might update your view (if anywhere)
- State what would change your mind

Deliver (max 300 words):
1. **Direct response** to their critique
2. **Strengthened argument** (new evidence or framing)
3. **Concessions** (where they have a point)
4. **Crux** (what we'd need to know to resolve this)
"""
)
```

**Step 2: Challenger responds** (after Step 1 completes)
```
Task(
  subagent_type="general-purpose",
  description="Dialogue: [Agent Y] responds",
  model="opus",
  prompt="""You are [AGENT Y's LENS] from Round 1.

You claimed: [Y's position from Round 1]

[AGENT X] has responded to your critique:
---
[PASTE AGENT X's RESPONSE FROM STEP 1]
---

Your task: RESPOND to their defense.
- Did they address your strongest point?
- Where does their argument still fail?
- Where did they change your mind (if anywhere)?
- What's the remaining disagreement (if any)?

Deliver (max 300 words):
1. **Assessment** of their response
2. **Remaining weaknesses** in their position
3. **Updated view** (where you shifted)
4. **Final verdict**: agreement, partial agreement, or persistent disagreement
"""
)
```

**Step 3: Synthesis of dialogue**

After both agents have spoken, synthesize the dialogue outcome:
- Did they converge? On what?
- What remains contested?
- What new insights emerged from the exchange?
- How does this change the overall analysis?

---

### Round 2: Depth (Launch 1-2 More Agents)

Based on the synthesis, launch targeted deep-dive agents:

**Deep-Dive Agent Template:**
```
Task(
  subagent_type="general-purpose",
  description="Deep-dive: [specific thread]",
  model="opus",
  prompt="""Explore this specific tension/gap in depth:

THREAD: [describe the contested point]

CONTEXT FROM ROUND 1:
[paste relevant excerpts from Round 1 agents]

Your task:
- Investigate the root cause of this disagreement
- Find evidence that resolves or clarifies it
- Propose a synthesis that honors both sides
- Identify what's truly unresolvable vs just underexplored

Deliver (max 400 words):
1. **Root analysis**
2. **Evidence/reasoning**
3. **Proposed resolution**
4. **Remaining uncertainty**
"""
)
```

**Red-Team Agent:**
```
Task(
  subagent_type="general-purpose",
  description="Red-team the emerging synthesis",
  model="opus",
  prompt="""Attack this emerging synthesis:

SYNTHESIS SO FAR:
[paste the intermediate synthesis]

Your job:
- Find the weakest link
- Identify what we're missing
- Challenge the consensus
- Propose what would falsify this view

Deliver (max 300 words):
1. **Weakest point in synthesis**
2. **Missing perspective**
3. **Falsification criteria**
4. **Final "gotcha" question**
"""
)
```

---

### Final Output Structure

After Round 2 completes, generate the final answer:

## Executive Synthesis
[10 lines max - the coherent narrative merging all perspectives]

## Consensus
[What all/most perspectives agree on - bullet points]

## Structured Disagreements
[For each major tension, use this format:]

### Disagreement 1: [Topic]
| Position A | Position B |
|------------|------------|
| **Claimed by**: [Agent(s)] | **Claimed by**: [Agent(s)] |
| **Argument**: [Core claim] | **Argument**: [Core claim] |
| **Because**: [Reasoning] | **Because**: [Reasoning] |

**The crux**: [What would need to be true for one side to be right]
**Resolution**: [How this was resolved, or why it remains unresolved]

[Repeat for each major disagreement. Do NOT smooth over conflicts.]

## Dialogue Outcome (from Round 1.5)
**Contested point**: [The #1 disagreement that went to dialogue]

| Turn | Agent | Key Move |
|------|-------|----------|
| Defense | [Agent X] | [Their main counter-argument] |
| Response | [Agent Y] | [Their assessment + any concessions] |

**Convergence**: [Where they agreed after dialogue]
**Persistent disagreement**: [What remains unresolved]
**New insight**: [What emerged from the exchange that wasn't in Round 1]

## Practical Guidance
[Actionable recommendations based on the analysis]

## Risks & Mitigations
[What could go wrong with the recommended approach]

## Confidence Assessment
| Claim | Confidence | Basis |
|-------|------------|-------|
| ... | High/Medium/Low | Fact/Inference/Speculation |

## Follow-Up Questions
[3-5 questions that would most sharpen understanding if answered]

---

## Design Philosophy

**Dynamic + Fixed agent mix:**
- 3 dynamic agents are generated based on the actual question (domain-relevant expertise)
- 3 fixed agents provide universal lenses (Contrarian, Systems, Pragmatist)
- Dynamic agents prevent wasted perspectives (no "Prompt Engineering lens" for pricing questions)
- Fixed agents ensure essential viewpoints are never skipped

**Bet on model intelligence:**
- Principles > rubrics
- Heuristics > rigid rules
- Structured output > scoring spreadsheets
- Let agents reason freely within their lens
- Synthesis merges insights, not scores

**Structured disagreement is the insight:**
- Explicit "A claims X because P, B claims Y because Q" beats vague "there are tradeoffs"
- The crux (what would make one side right) is often more valuable than the resolution
- Unresolved tensions are valid outputs — don't force false consensus
- Depth comes from confronting conflicts, not spawning more agents

**Adversarial dialogue produces real convergence:**
- Parallel monologues miss each other's points; dialogue forces engagement
- Defender must address the strongest counterargument, not a strawman
- Concessions are explicit — "you changed my mind on X" is a valuable signal
- Two rounds of exchange is usually enough; more risks performative debate

**Avoid:**
- Point-based rubrics that narrow reasoning
- Overly deterministic formats
- Forcing agents into identical output structures
- Premature consensus (honor real disagreements)
- Smoothing over disagreements in synthesis
