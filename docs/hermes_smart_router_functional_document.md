# Hermes Smart Router Functional Requirements Document

## 1. Product Name

**Hermes Smart Router**

A terminal-based routing plugin for Hermes that selects the best available LLM model for each task across subscription providers, OAuth providers, API providers, and local models.

The system must support both deterministic tier routing and intelligent auto routing. It must account for subscription limits, provider availability, model equivalence, fallback providers, learning memory, cost savings, and provider recovery.

---

## 2. Product Goal

Build a Hermes plugin that acts like **VS Code Copilot Auto Mode**, but for all models available inside Hermes, with a terminal-first interface that is keyboard driven, cost aware, and easy for users to control.

The router should select the best model for each request based on:

- Task complexity
- Required capability
- Provider availability
- Subscription limits
- Model equivalence
- Cost
- Latency
- Historical success
- Future provider preservation
- Fallback availability
- User overrides and confirmations

The system should prioritise subscription-backed and local models before paid API fallbacks.

When multiple models are equally capable, the router should choose the cheapest competent option and preserve more flexible providers for tasks that need their unique models.

---

## 3. Core Problem

Hermes can support multiple providers and models, including OAuth-based providers such as GitHub Copilot and ChatGPT Codex. However, users need a smarter way to select which model should handle each task.

The router must solve these problems:

- Avoid manually switching models.
- Avoid wasting premium subscription requests.
- Avoid using paid APIs when subscription or local options are available.
- Detect when providers are unavailable or quota-limited.
- Remove unavailable providers from routing.
- Re-add providers when they recover.
- Treat the same model from different providers as equivalent but not identical.
- Preserve flexible providers for tasks that need their unique models.
- Learn over time which models perform best for which tasks.

---

## 4. Design Philosophy

The router should think like this:

> Use the cheapest competent model that is currently available, while preserving future routing options.

This means the router should not always choose the strongest model. It should choose the lowest-cost model that is likely to complete the task correctly.

It should also protect flexible providers. For example:

- GitHub Copilot may provide GPT, Claude, and Gemini models.
- ChatGPT Codex may provide GPT models only.

If a task requires GPT and both Codex GPT and Copilot GPT are available, the router should normally choose Codex GPT first. This preserves Copilot quota for tasks that may need Claude or Gemini.

---

## 5. Target Environment

The plugin is designed for:

- Hermes terminal users
- Hermes Workspace users
- Users with multiple model providers
- Users with OAuth subscription providers
- Users with local models
- Users who want minimal API spend
- Users who want routing analytics and cost savings visibility

Primary providers expected:

- GitHub Copilot OAuth
- ChatGPT Codex OAuth
- Gemini OAuth
- Ollama local models
- OpenAI API
- Anthropic API
- DeepSeek API
- OpenRouter API
- Any Hermes-supported custom provider

### 5.1 Backend Plugin Communication

The router runs as a backend plugin, not as a standalone desktop app.

The user interacts with it through two channels:

- The Hermes AI chat for runtime messages, confirmations, warnings, and routing summaries
- The terminal interface for initial setup, configuration, diagnostics, and maintenance

The plugin must be able to push concise messages into the user's active Hermes chat when important routing events occur, such as:

- Provider limit reached
- Smart routing fallback to tier routing
- Paid API confirmation required
- Provider recovered after probing
- Cost guardrail triggered

The chat messages should be short, actionable, and safe to read without opening the terminal UI.

### 5.2 Installer and Setup Flow

The project must include an installer path that is simple enough for a user to copy one command from GitHub, paste it into a terminal, and let the setup complete automatically.

The installer should:

- Clone or download the repository into the correct local location
- Detect and install required dependencies
- Create or migrate local config and storage files
- Register the backend plugin with Hermes
- Verify Hermes can see the plugin and its provider integrations
- Launch the HermesRouter setup flow in the terminal
- Leave the user ready to configure routing preferences, providers, and guardrails

The README or GitHub release page should expose the install command clearly so the user does not need to assemble setup steps manually.

---

## 6. Main Features

### 6.1 Routing Modes

The plugin must support two primary routing modes:

1. **Tier Routing**
2. **Smart Auto Routing**

Smart Auto Routing must fall back to Tier Routing when auto routing fails.

---

## 7. Routing Mode 1: Tier Routing

Tier Routing is deterministic.

The user configures five capability tiers. Each tier contains:

- Tier name
- Tier purpose
- Primary model
- Fallback model
- Optional secondary fallback
- Provider priority
- Whether fallback API models are allowed

### 7.1 Default Tiers

| Tier | Purpose | Example Use |
|---|---|---|
| T1 | Cheap and simple | Small questions, formatting, basic transforms |
| T2 | Fast general | Summaries, simple generation, short analysis |
| T3 | Balanced | Normal coding, planning, document drafting |
| T4 | Strong | Complex coding, multi-step reasoning, tool-heavy work |
| T5 | Premium | Critical reasoning, legal analysis, high-risk output, advanced architecture |

### 7.2 Tier Selection Logic

The router evaluates the prompt and maps it to a tier.

Inputs:

- Prompt length
- Task type
- Need for code
- Need for reasoning
- Risk level
- Tool use requirement
- Required context size
- User-selected preference
- Historical success patterns

Example mapping:

```text
Simple rewrite              -> T1
Short summary               -> T2
Normal Python script         -> T3
Complex app debugging        -> T4
Critical legal/GDPR analysis -> T5
```

### 7.3 Tier Failure Handling

If the primary model fails:

1. Try the tier fallback.
2. Try the secondary fallback if configured.
3. Escalate to the next tier if allowed.
4. Use fallback provider only if all normal providers in the required class are unavailable.
5. Notify the user if no model is available.

---

## 8. Routing Mode 2: Smart Auto Routing

Smart Auto Routing uses a routing LLM or routing classifier to decide which available model should handle each request.

The user selects:

- Allowed providers
- Routing LLM
- Routing strategy
- Fallback behaviour
- API fallback permission
- Provider preservation preference
- Cost priority
- Latency priority
- Quality priority

### 8.1 Smart Routing Inputs

The router receives:

- Current user prompt
- Current timestamp
- User timezone
- Day of week
- Available providers
- Available models
- Provider health states
- User-selected allowed providers
- Estimated quota state
- Cooldown states
- Model equivalence groups
- Historical success data
- Estimated costs
- Recent failures
- User preferences

The routing LLM must only choose from the user-approved provider set and the currently available candidate models.

### 8.2 Smart Routing Output

The routing LLM must return structured JSON only.

Example:

```json
{
  "selected_provider": "codex",
  "selected_model": "gpt-5.4",
  "fallback_provider": "copilot",
  "fallback_model": "gpt-5.4",
  "routing_reason": "Task requires strong GPT reasoning. Codex is less flexible than Copilot, so Codex should be used first to preserve Copilot quota for Claude-only tasks.",
  "confidence": 91,
  "tier_equivalent": "T5",
  "allow_api_fallback": false
}
```

### 8.3 Auto Routing Failure Conditions

Smart Auto Routing is considered failed if:

- Routing LLM is unavailable.
- Routing LLM returns invalid JSON.
- Routing confidence is below the configured threshold.
- Selected provider is unavailable.
- Selected model is unavailable.
- Provider quota is exhausted.
- Provider execution fails repeatedly.
- Routing decision violates provider rules.
- Routing decision selects a fallback provider while normal providers are still available in the same capability group.

If auto routing fails, the router must fall back to Tier Routing without requiring the user to re-enter the prompt.

### 8.4 Auto to Tier Fallback

If Smart Auto Routing fails, the router must fall back to Tier Routing.

Fallback flow:

```text
Smart Auto Routing
    ↓
Fails or confidence too low
    ↓
Map task to tier
    ↓
Use configured tier primary model
    ↓
Use configured tier fallback if needed
    ↓
Use fallback provider only if normal providers unavailable
```

The user should be notified only if the fallback materially changes cost, quality, or provider use.

Example notification:

```text
Auto routing failed. Switched to Tier Routing: T4 Strong.
Selected: Copilot Claude.
Reason: Routing model unavailable.
```

---

## 9. Provider Types

The system must support two provider types.

### 9.1 Normal Providers

Normal providers are used before fallback providers.

Examples:

- GitHub Copilot OAuth
- ChatGPT Codex OAuth
- Gemini OAuth
- Ollama local

### 9.2 Fallback Providers

Fallback providers are normally hidden from routing.

They become available only when all equivalent normal provider models are unavailable.

Examples:

- DeepSeek API
- OpenRouter API
- OpenAI API
- Anthropic API

### 9.3 Fallback Provider Rule

If there are three equivalent models:

| Provider | Type | Status |
|---|---|---|
| Codex GPT-5.4 | Normal | Available |
| Copilot GPT-5.4 | Normal | Available |
| DeepSeek API equivalent | Fallback | Standby |

The fallback provider must remain unavailable.

If both normal providers become unavailable:

| Provider | Type | Status |
|---|---|---|
| Codex GPT-5.4 | Normal | Unavailable |
| Copilot GPT-5.4 | Normal | Unavailable |
| DeepSeek API equivalent | Fallback | Active |

The fallback provider becomes active.

---

## 10. Model Equivalence Groups

The router must understand that the same or similar models can exist across different providers.

Example:

```text
GitHub Copilot - GPT-5.4 - available
ChatGPT Codex - GPT-5.4 - available
OpenAI API - GPT-5.4 - fallback standby
```

These models may be equivalent in capability, but they are not equivalent in cost, quota, or provider flexibility.

### 10.1 Equivalence Group Example

```json
{
  "group_id": "gpt_5_4_class",
  "capability_class": "premium_reasoning",
  "models": [
    {
      "provider": "codex",
      "model": "gpt-5.4",
      "provider_type": "normal",
      "priority": 1
    },
    {
      "provider": "copilot",
      "model": "gpt-5.4",
      "provider_type": "normal",
      "priority": 2
    },
    {
      "provider": "openai_api",
      "model": "gpt-5.4",
      "provider_type": "fallback",
      "priority": 3
    }
  ]
}
```

---

## 11. Provider Flexibility Preservation

The router must account for provider flexibility.

A provider that offers many unique models should be preserved where possible.

Example:

| Provider | Models |
|---|---|
| Codex | GPT only |
| Copilot | GPT, Claude, Gemini |

If a GPT task can be handled by Codex or Copilot, choose Codex first.

Reason:

```text
Codex can only handle GPT-class tasks.
Copilot can handle GPT, Claude, and Gemini tasks.
Preserve Copilot for tasks where Codex is not useful.
```

### 11.1 Provider Flexibility Score

Each provider gets a flexibility score based on:

- Number of model families available
- Number of unique models available
- Whether models are available elsewhere
- Current quota level
- Historical reliability

Lower flexibility providers are preferred first when capability is equal.

---

## 12. Provider Health Engine

The router must maintain a real-time health state for each provider and model.

### 12.1 Provider Health States

Allowed states:

| State | Meaning |
|---|---|
| AVAILABLE | Provider can be used |
| LIMITED | Provider works but quota or performance may be degraded |
| RATE_LIMITED | Temporary rate limit detected |
| SUBSCRIPTION_LIMIT | Subscription or premium request limit reached |
| AUTH_REQUIRED | OAuth or token refresh required |
| UNAVAILABLE | Provider cannot currently be used |
| COOLDOWN | Provider is paused until recovery check |
| PROBING | Provider is being checked for recovery |
| UNKNOWN | Health is not known |
| STANDBY | Fallback provider is healthy but not active |

### 12.2 Provider State Object

```json
{
  "provider_id": "copilot",
  "provider_name": "GitHub Copilot",
  "provider_type": "normal",
  "status": "AVAILABLE",
  "quota_state": "healthy",
  "estimated_remaining": null,
  "cooldown_until": null,
  "next_probe_at": null,
  "last_success_at": "2026-05-12T10:12:00+02:00",
  "last_failure_at": null,
  "last_error_type": null,
  "failure_rate": 0.02,
  "timezone": "Europe/Malta"
}
```

---

## 13. Provider Availability Checks

The router must not rely only on saved configuration.

It must validate provider availability dynamically.

### 13.1 Before Each Request

The router must check:

- Provider status
- Model status
- OAuth validity if known
- Recent failures
- Cooldown state
- Quota state
- Whether fallback provider is allowed

### 13.2 After Each Request

The router must update health state based on:

- Success
- Failure
- Error message
- Rate limit message
- Quota message
- Auth error
- Timeout
- Provider crash
- Model unavailable message

### 13.3 Opportunistic Checks

Before using a paid fallback provider, the router should check if a subscription provider may have recovered.

Example:

```text
Task requires GPT-5.4.
Codex is in cooldown.
Copilot is exhausted.
OpenAI API fallback is available.
Before spending API money, probe Codex if probing is allowed.
```

---

## 14. Subscription Limit Handling

Subscription providers may have request limits, weekly limits, daily limits, or premium request limits.

Examples:

- GitHub Copilot premium requests
- ChatGPT Codex usage limits
- Gemini OAuth limits

The router must detect these limits and remove affected models from active routing.

### 14.1 Limit Detection Methods

The system uses three methods.

#### Method 1: Provider Message Interpretation

The provider may return a message such as:

```text
Premium request limit reached.
Try again tomorrow.
Weekly quota exceeded.
You have reached your usage limit.
This model is temporarily unavailable.
```

The system must interpret the message and classify it.

#### Method 2: Rolling Usage Estimates

The system tracks usage patterns and estimates quota state.

Example:

```text
Copilot Claude usually reaches limit around 120 premium requests per week.
Current week: 102 estimated requests.
Warning threshold: 85 percent.
```

#### Method 3: Provider Probing

The system sends a minimal test request to check if the provider is usable.

Example probe:

```text
Reply with exactly: OK
```

### 14.2 Limit Reached Behaviour

When a provider limit is confirmed:

1. Set provider or model state to `SUBSCRIPTION_LIMIT`.
2. Remove affected models from active routing.
3. Keep equivalent fallback normal providers available.
4. Activate fallback API provider only if all normal providers in the capability group are unavailable.
5. Notify the user.
6. Schedule recovery check.

Example notification:

```text
Codex GPT-5.4 limit reached.
Removed from active routing.
Copilot GPT-5.4 remains available.
Next recovery check: 6 hours.
```

---

## 15. Provider Message Interpretation

Provider messages can vary. The router must normalise them into standard categories.

### 15.1 Standard Error Categories

```text
SUBSCRIPTION_LIMIT
RATE_LIMIT
TEMPORARY_FAILURE
AUTH_FAILURE
MODEL_UNAVAILABLE
NETWORK_FAILURE
PROVIDER_OUTAGE
INVALID_REQUEST
UNKNOWN
```

### 15.2 Interpretation Stack

The system should use a layered interpretation model.

#### Stage 1: Regex and Keyword Detection

Fast, local, zero cost.

Detect common phrases:

```text
premium request limit
weekly limit
quota exceeded
rate limit
try again later
model unavailable
authentication required
invalid token
```

#### Stage 2: Local LLM Interpreter

If regex confidence is low, use a local model.

Examples:

- Qwen small
- Phi small
- Gemma small
- Any local Ollama model

The local LLM classifies provider messages into standard categories.

#### Stage 3: Cheap Normal Provider Interpreter

If local interpretation confidence is low, use the cheapest available normal provider.

#### Stage 4: Cheapest Fallback Provider Interpreter

Only if all normal interpretation options fail.

Use the cheapest fallback provider to classify the error.

### 15.3 Interpretation Output

```json
{
  "category": "SUBSCRIPTION_LIMIT",
  "confidence": 94,
  "retry_after": "2026-05-13T00:00:00+02:00",
  "human_summary": "Provider says the weekly premium request limit has been reached."
}
```

---

## 16. Timestamp Handling

Every routing and interpretation LLM must receive a timestamp.

The timestamp must include:

- Current date
- Current time
- Timezone
- Day of week
- UTC offset

Example:

```json
{
  "current_timestamp": "2026-05-12T11:25:00+02:00",
  "timezone": "Europe/Malta",
  "day_of_week": "Tuesday",
  "utc_offset": "+02:00"
}
```

### 16.1 Why Timestamp Is Required

Provider messages may say:

```text
Try again tomorrow.
Resets next week.
Available after 04:00 UTC.
Premium requests reset on Sunday.
```

The LLM cannot interpret this correctly unless it knows the current date and time.

---

## 17. Provider Recovery Engine

The router must detect when an unavailable provider becomes available again.

### 17.1 Provider Lifecycle

```text
AVAILABLE
    ↓
LIMIT_REACHED
    ↓
COOLDOWN
    ↓
PROBING
    ↓
AVAILABLE
```

or:

```text
AVAILABLE
    ↓
TEMPORARY_FAILURE
    ↓
PROBING
    ↓
AVAILABLE
```

### 17.2 Recovery Detection Methods

#### Method 1: Message-Based Reset Time

If the provider gives a reset time, use it.

Example message:

```text
Premium requests reset in 3 days.
```

The interpreter returns:

```json
{
  "estimated_reset": "2026-05-15T00:00:00+02:00",
  "next_probe_at": "2026-05-15T00:10:00+02:00"
}
```

No probing should happen before this time unless the user manually triggers it.

#### Method 2: Scheduled Probing

If reset time is unknown, use scheduled probes.

Probe schedule depends on failure type.

##### Temporary Failure Probe Schedule

```text
15 minutes
30 minutes
1 hour
2 hours
4 hours
```

##### Subscription Limit Probe Schedule

```text
6 hours
12 hours
24 hours
```

##### Unknown Failure Probe Schedule

```text
1 hour
2 hours
4 hours
8 hours
```

#### Method 3: Opportunistic Recovery Probe

Before using a paid API fallback, probe the subscription provider if:

- The task requires the same capability class.
- The provider cooldown has passed or is close to expiry.
- Probing is allowed by user settings.
- The probe will not burn significant quota.

### 17.3 Stop Probing Rule

Once a provider probe succeeds:

1. Set provider status to `AVAILABLE`.
2. Clear cooldown.
3. Clear next probe time.
4. Re-add provider models to routing.
5. Stop scheduled probing.
6. Notify the user if configured.

Example:

```text
Codex is available again.
GPT-5.4 has been restored to active routing.
```

---

## 18. Probe Design

Probes must be low cost and safe.

Default probe prompt:

```text
Reply with exactly: OK
```

Expected response:

```text
OK
```

### 18.1 Probe Rules

- Do not probe healthy providers unnecessarily.
- Do not probe fallback providers unless needed.
- Do not repeatedly probe subscription providers in a tight loop.
- Respect cooldowns.
- Use exponential backoff.
- Stop probing once provider is available.
- Record all probe outcomes.

---

## 19. Routing Decision Formula

The router should score candidates using:

```text
score =
  task_fit
+ model_capability
+ provider_health
+ quota_remaining
+ historical_success
+ provider_preservation_value
+ latency_score
- estimated_cost
- failure_risk
```

The primary optimisation rule is: use the cheapest competent model that is currently available, then preserve higher-flexibility providers and paid API fallback options for cases where they are uniquely needed.

### 19.1 Key Scoring Factors

| Factor | Meaning |
|---|---|
| task_fit | How well the model matches the task |
| model_capability | Reasoning, coding, context, tool use strength |
| provider_health | Whether provider is reliable now |
| quota_remaining | Estimated remaining subscription capacity |
| historical_success | Past success on similar tasks |
| provider_preservation_value | Whether provider should be saved for unique models |
| latency_score | Expected speed |
| estimated_cost | API or equivalent cost |
| failure_risk | Risk of bad output or provider failure |

### 19.2 Cost Optimisation Rules

The router should apply these rules when scores are close:

- Prefer local models first when they are competent for the task.
- Prefer subscription or OAuth-backed models over paid API models.
- Prefer the least flexible provider when capability is equal.
- Prefer the provider that is most likely to preserve scarce quota for later tasks.
- Avoid paid API fallback unless all normal providers in the capability group are unavailable or the user explicitly allows it.
- Surface estimated cost before execution when the selected route may incur spend.

---

## 20. Learning Memory

Learning Memory is a Phase 2 feature.

It makes the router smarter, faster, cheaper, and more specific to the user over time.

### 20.1 What It Stores

Every run should be logged.

Example:

```json
{
  "request_id": "uuid",
  "timestamp": "2026-05-12T11:40:00+02:00",
  "task_type": "python_debugging",
  "prompt_length": 3200,
  "selected_provider": "codex",
  "selected_model": "gpt-5.4",
  "routing_mode": "smart_auto",
  "fallback_used": false,
  "latency_seconds": 14.2,
  "estimated_cost": 0,
  "api_equivalent_cost": 0.82,
  "success_score": 9,
  "user_retry": false,
  "provider_error": null
}
```

### 20.2 Learning Uses

The router should learn:

- Which models work best for each task type.
- Which providers fail often.
- Which provider messages mean quota exhaustion.
- When providers usually recover.
- Which fallback chains work best.
- Which local models are good enough.
- When using a premium model was unnecessary.
- When a cheap model caused retries.

### 20.3 Similar Task Lookup

Before asking the routing LLM, the system should check memory.

Flow:

```text
New prompt
    ↓
Extract task features
    ↓
Find similar past tasks
    ↓
Recommend known good model
    ↓
Routing LLM validates or overrides
```

### 20.4 Success Scoring

The system should estimate success using signals:

| Signal | Meaning |
|---|---|
| User accepted output | Positive |
| User retried request | Negative |
| User escalated model manually | Negative for first model |
| Tool completed successfully | Positive |
| Provider failed | Negative |
| Output required heavy editing | Slight negative |
| Cheap model succeeded | Strong positive |
| Fallback API was avoided | Positive |

---

## 21. Cost Tracking and Savings

The router must track both real cost and equivalent cost.

### 21.1 Cost Types

| Type | Meaning |
|---|---|
| Actual cost | Real API spend |
| Equivalent cost | What the same task would have cost via API |
| Saved cost | Equivalent cost minus actual cost |
| Subscription value | Estimated value extracted from subscription models |

Example:

```text
Codex GPT task
API equivalent: $0.81
Actual spend: $0
Saved: $0.81
```

The router should maintain both per-run and cumulative savings so the user can see whether smart routing is actually reducing spend.

### 21.2 Cost Dashboard

The terminal UI should show:

```text
Today saved: $8.12
This month saved: $148.42
API spend: $3.20
Fallback API avoided: 42 runs
Best cheap model: Qwen local
Most reliable provider: Codex
Most preserved provider: Copilot
```

### 21.3 Cost Guardrails

Users should be able to define cost controls such as:

- Maximum acceptable API spend per run
- Daily or weekly spend warnings
- Whether the router may auto-escalate to paid APIs
- Whether paid API use requires confirmation
- Whether fallback APIs are hidden unless manually enabled

If the selected route exceeds the configured guardrail, the router should either switch to a cheaper eligible model or prompt the user for confirmation.

---

## 22. Auto Price Fetching

The system should fetch pricing data automatically where possible.

### 22.1 Price Sources

Supported pricing sources may include:

- OpenRouter model registry
- LiteLLM model pricing map
- Official OpenAI pricing
- Official Anthropic pricing
- Official DeepSeek pricing
- User-defined price overrides

### 22.2 Price Cache

Prices should be cached locally.

Example:

```json
{
  "model": "claude-sonnet",
  "provider": "anthropic_api",
  "input_per_1m": 3.0,
  "output_per_1m": 15.0,
  "currency": "USD",
  "updated_at": "2026-05-12T09:00:00+02:00"
}
```

### 22.3 Update Schedule

Default:

```text
Daily price sync
Manual refresh option
Fallback to cached prices if offline
```

---

## 23. Terminal Interface

The plugin must use a terminal interface that matches the Hermes terminal style.

### 23.1 UI Requirements

The terminal UI must support:

- Arrow key navigation
- Checkboxes
- Selectable lists
- Tables
- Keyboard shortcuts
- Dark colour scheme matching Hermes
- Consistent checkbox and arrow-key navigation patterns
- Provider health screen
- Routing configuration screen
- Analytics screen
- Cost screen
- Logs screen

Recommended Python libraries:

- Textual
- Prompt Toolkit
- Rich

### 23.2 Main Menu

```text
Hermes Smart Router

[ ] Rule Based Routing
[ ] Smart Auto Routing

Options:
> Configure Providers
  Configure Tiers
  Configure Smart Router
  Provider Health
  Cost and Savings
  Learning Memory
  Routing Rules
  Notification Settings
  Logs
  Save and Exit
```

### 23.3 Tier Routing Screen

```text
Tier   Purpose          Primary              Fallback
------------------------------------------------------------
T1     Cheap/simple     Ollama Qwen           Gemini Flash
T2     Fast general     Gemini Flash          Copilot GPT
T3     Balanced         Codex GPT             Copilot GPT
T4     Strong           Copilot Claude        Codex GPT
T5     Premium          Codex GPT-5.4         Copilot GPT-5.4
```

User can select a tier and edit:

- Primary provider
- Primary model
- Fallback provider
- Fallback model
- API fallback allowed
- Escalation allowed

### 23.4 Smart Routing Screen

```text
Smart Auto Routing

Allowed Providers:
[x] ChatGPT Codex
[x] GitHub Copilot
[x] Gemini OAuth
[x] Ollama Local
[ ] OpenAI API
[ ] Anthropic API
[x] DeepSeek API fallback

Routing LLM:
> Ollama Qwen Local

Optimisation:
( ) Cheapest
(x) Balanced
( ) Best Quality
( ) Lowest Latency

Fallback:
[x] Auto fallback to Tier Routing
[x] Retry stronger model on failure
[x] Use API fallback only when normal providers unavailable
```

The smart routing screen should also let the user pin preferred providers, exclude providers, set a confidence threshold, and toggle whether cost or latency takes priority when quality is similar.

### 23.5 Provider Health Screen

```text
Provider Health

Provider        Status              Notes
-----------------------------------------------------
Codex           Available           GPT models active
Copilot         Limited             Premium use high
Gemini          Available           Healthy
Ollama          Available           Local
DeepSeek API    Standby             Fallback only
OpenAI API      Standby             Fallback only
```

### 23.6 Cooldown Screen

```text
Cooldowns and Recovery

Provider   Reason              Next Probe        Estimated Reset
------------------------------------------------------------------
Codex      Subscription Limit  6h 12m            Unknown
Copilot    Rate Limited        22m               2026-05-12 14:00
```

### 23.7 Analytics Screen

```text
Routing Analytics

Runs today: 48
Auto routed: 39
Tier routed: 9
Auto to tier fallbacks: 4
API fallback runs: 2
Estimated savings today: $8.12
Estimated savings this month: $148.42
Most successful model: Copilot Claude
Best cheap model: Ollama Qwen
```

### 23.8 Control Screen

```text
Routing Controls

[x] Require confirmation before paid API use
[x] Auto-hide exhausted providers
[x] Auto-fall back from Smart Routing to Tier Routing
[x] Probe providers for recovery
[ ] Verbose routing notifications

Budget Guardrails:
  Daily API spend warning: $5.00
  Weekly API spend warning: $20.00
  Per-run confirmation threshold: $0.50
```

---

## 24. User Notifications

The router should notify the user when important routing state changes occur.

Notifications should be concise, actionable, and tied to a specific routing outcome so the user knows what changed and why.

Notify when:

- A provider limit is reached.
- A provider is removed from routing.
- A provider recovers.
- Smart routing falls back to Tier Routing.
- A fallback API provider is activated.
- A paid API provider is about to be used, if confirmation is enabled.
- A routing decision has low confidence.
- A cost guardrail was triggered.
- A provider was restored after probing.
- The router is preserving quota by selecting a less flexible provider.

Do not notify for every normal routing decision unless verbose mode is enabled.

### 24.1 Notification Levels

- Info: routine state changes such as provider recovery
- Warning: provider limit reached, low confidence, or tier fallback
- Confirmation: paid API use, if the user requires approval
- Blocking: no eligible model is available

### 24.2 User Control Rules

The user should be able to:

- Enable or disable providers and models
- Pin a provider or model for specific tiers
- Hide fallback providers until manual activation
- Set confidence thresholds for auto routing
- Require confirmation before paid API usage
- Force Tier Routing for specific tasks or prompts
- Reset routing preferences and memory when needed

---

## 25. Configuration System

The system must save configuration locally.

### 25.1 Main Config Example

```json
{
  "routing_mode": "smart_auto",
  "auto_fallback_to_tier": true,
  "timezone": "Europe/Malta",
  "confidence_threshold": 75,
  "allow_api_fallback": true,
  "require_confirmation_for_paid_api": true,
  "max_api_spend_per_run": 0.5,
  "daily_api_spend_warning": 5.0,
  "weekly_api_spend_warning": 20.0,
  "provider_preservation_enabled": true,
  "learning_memory_enabled": true,
  "cost_tracking_enabled": true,
  "probe_enabled": true
}
```

### 25.2 Provider Config Example

```json
{
  "providers": [
    {
      "id": "codex",
      "name": "ChatGPT Codex",
      "type": "normal",
      "auth_type": "oauth",
      "enabled": true,
      "preserve_for_unique_models": false
    },
    {
      "id": "copilot",
      "name": "GitHub Copilot",
      "type": "normal",
      "auth_type": "oauth",
      "enabled": true,
      "preserve_for_unique_models": true
    },
    {
      "id": "deepseek_api",
      "name": "DeepSeek API",
      "type": "fallback",
      "auth_type": "api_key",
      "enabled": true,
      "standby_only": true
    }
  ]
}
```

### 25.3 User Preference Example

```json
{
  "prefer_local_first": true,
  "prefer_cheapest_competent": true,
  "require_prompt_before_paid_api": true,
  "hide_fallback_providers": true,
  "pin_tier_models": {
    "T3": {
      "provider": "codex",
      "model": "gpt-5.4"
    }
  }
}
```

### 25.4 Tier Config Example

```json
{
  "tiers": [
    {
      "tier": "T1",
      "name": "Cheap Simple",
      "primary": {
        "provider": "ollama",
        "model": "qwen-local"
      },
      "fallback": {
        "provider": "gemini",
        "model": "flash"
      }
    },
    {
      "tier": "T5",
      "name": "Premium Reasoning",
      "primary": {
        "provider": "codex",
        "model": "gpt-5.4"
      },
      "fallback": {
        "provider": "copilot",
        "model": "gpt-5.4"
      }
    }
  ]
}
```

---

## 26. Database

Use SQLite for local storage.

### 26.1 Tables

Recommended tables:

```text
providers
models
provider_health
model_equivalence_groups
routing_runs
routing_decisions
provider_errors
provider_probes
cost_logs
price_cache
learning_memory
user_overrides
```

### 26.2 Provider Health Table

Fields:

```text
id
provider_id
model_id
status
reason
quota_state
estimated_remaining
cooldown_until
next_probe_at
last_success_at
last_failure_at
failure_count
probe_count
updated_at
```

### 26.3 Routing Runs Table

Fields:

```text
id
timestamp
prompt_hash
task_type
routing_mode
selected_provider
selected_model
fallback_used
auto_to_tier_fallback
latency_seconds
success_score
estimated_cost
api_equivalent_cost
actual_cost
error_category
created_at
```

---

## 27. Core Modules

Suggested file structure:

```text
hermes-smart-router/

README.md
pyproject.toml
plugin.py

src/hermes_smart_router/
    __init__.py
    plugin.py
    config.py
    constants.py

    routing/
        router_engine.py
        smart_router.py
        tier_router.py
        fallback_router.py
        scoring.py
        task_classifier.py

    providers/
        provider_scanner.py
        provider_health.py
        provider_recovery.py
        provider_probe.py
        provider_registry.py
        model_registry.py
        model_equivalence.py

    interpretation/
        error_interpreter.py
        regex_interpreter.py
        local_llm_interpreter.py
        provider_llm_interpreter.py

    learning/
        memory.py
        similarity.py
        success_scoring.py
        recovery_prediction.py

    cost/
        price_fetcher.py
        price_cache.py
        cost_estimator.py
        savings_tracker.py

    ui/
        terminal_app.py
        screens_main.py
        screens_tiers.py
        screens_smart.py
        screens_health.py
        screens_cost.py
        theme.py

    storage/
        db.py
        migrations.py
        repositories.py

    utils/
        time_utils.py
        json_utils.py
        logging.py
        hashing.py
```

---

## 28. Core Workflows

### 28.1 Smart Auto Routing Workflow

```text
Receive prompt
    ↓
Load current timestamp
    ↓
Refresh provider health snapshot
    ↓
Remove unavailable providers
    ↓
Hide fallback providers unless eligible
    ↓
Build candidate model list
    ↓
Check learning memory
    ↓
Ask routing LLM
    ↓
Validate routing decision
    ↓
Execute selected model
    ↓
Interpret result or error
    ↓
Update provider health
    ↓
Update cost logs
    ↓
Update learning memory
```

### 28.2 Auto to Tier Fallback Workflow

```text
Smart routing fails
    ↓
Classify task into tier
    ↓
Load tier config
    ↓
Select tier primary model
    ↓
Validate provider availability
    ↓
Execute
    ↓
Use tier fallback if needed
    ↓
Log auto_to_tier_fallback = true
```

### 28.3 Provider Limit Workflow

```text
Provider returns error
    ↓
Interpret error
    ↓
Classify as SUBSCRIPTION_LIMIT
    ↓
Estimate reset time if possible
    ↓
Set provider/model cooldown
    ↓
Remove from routing
    ↓
Schedule probe
    ↓
Notify user
```

### 28.4 Provider Recovery Workflow

```text
Provider in cooldown
    ↓
Wait until next_probe_at
    ↓
Send minimal probe
    ↓
If success:
        mark available
        restore models
        stop probing
    ↓
If failure:
        update cooldown
        schedule next probe
```

### 28.5 Fallback Provider Activation Workflow

```text
Task requires capability group
    ↓
Normal providers checked
    ↓
All normal providers unavailable
    ↓
Activate fallback provider for that group
    ↓
Use cheapest eligible fallback
    ↓
Log fallback activation
```

---

## 29. Routing Prompt Template

The Smart Router LLM should receive a strict prompt.

```text
You are the Hermes Smart Router.

Your job is to choose the cheapest competent model for the current task while preserving future provider flexibility.

Current timestamp:
{timestamp}

Timezone:
{timezone}

Day of week:
{day_of_week}

User prompt:
{user_prompt}

Available providers and models:
{available_models}

Provider health:
{provider_health}

Model equivalence groups:
{equivalence_groups}

Historical performance:
{history_summary}

Rules:
1. Do not select unavailable providers.
2. Do not select fallback providers if normal equivalent providers are available.
3. Prefer subscription or local models before paid API models.
4. Prefer the least flexible provider when capability is equivalent.
5. Preserve providers that offer unique model families.
6. Use the cheapest competent model.
7. Escalate only when needed.
8. Return JSON only.

Return:
{
  "selected_provider": "",
  "selected_model": "",
  "fallback_provider": "",
  "fallback_model": "",
  "tier_equivalent": "",
  "confidence": 0,
  "routing_reason": "",
  "risk_notes": "",
  "allow_api_fallback": false
}
```

---

## 30. Provider Error Interpretation Prompt

```text
You are the Hermes Provider Error Interpreter.

Current timestamp:
{timestamp}

Timezone:
{timezone}

Provider:
{provider}

Model:
{model}

Raw provider message:
{raw_message}

Classify the message into one category:
- SUBSCRIPTION_LIMIT
- RATE_LIMIT
- TEMPORARY_FAILURE
- AUTH_FAILURE
- MODEL_UNAVAILABLE
- NETWORK_FAILURE
- PROVIDER_OUTAGE
- INVALID_REQUEST
- UNKNOWN

If the message indicates a reset time, calculate the estimated reset timestamp using the current timestamp.

Return JSON only:
{
  "category": "",
  "confidence": 0,
  "retry_after": null,
  "estimated_reset": null,
  "should_probe": true,
  "summary": ""
}
```

---

## 31. MVP Scope

The first version should include:

### Required MVP Features

- Terminal UI
- Hermes-style theme
- Provider discovery from Hermes where possible
- Manual provider configuration
- Tier Routing
- Smart Auto Routing
- Auto Routing fallback to Tier Routing
- Normal provider vs fallback provider logic
- Provider health state tracking
- Basic provider message interpretation
- Basic cooldown handling
- Basic probing
- Model equivalence groups
- Provider flexibility scoring
- Basic cost logging
- SQLite storage
- Config export/import

### Out of MVP Scope

- Advanced learning memory
- Full price auto-sync
- Full analytics dashboard
- Advanced recovery prediction
- Automatic benchmark testing
- Cloud sync
- Multi-user mode

---

## 32. Phase 2 Scope

Phase 2 adds intelligence and optimisation.

### Phase 2 Features

- Learning memory
- Similar task retrieval
- Historical success scoring
- Provider recovery prediction
- Provider phrase learning
- Cost savings dashboard
- Auto price fetching
- Usage trend analysis
- Quota estimation
- Subscription value tracking
- Better local LLM interpretation
- Better fallback chain optimisation
- Per-task model recommendations
- Manual user feedback scoring

---

## 33. Phase 3 Scope

Phase 3 adds advanced automation.

### Phase 3 Features

- Self-tuning routing policies
- Auto-generated model capability profiles
- Benchmark mode
- Team-shared routing profiles
- Cloud backup of non-sensitive config
- Workspace dashboard integration
- Exportable analytics reports
- Plugin marketplace packaging
- Public GitHub templates
- Community model registry

---

## 34. Security and Privacy Requirements

The router must protect sensitive data.

Requirements:

- Store API keys only through Hermes or secure local secret handling.
- Do not log raw prompts by default.
- Store prompt hashes unless user enables full logging.
- Keep learning memory local by default.
- Allow the user to clear memory.
- Allow the user to disable cost tracking.
- Allow the user to disable provider probing.
- Do not send provider error messages to paid LLMs unless required.
- Prefer local interpretation first.

---

## 35. Logging Requirements

Logs should include:

- Routing decision
- Selected provider
- Selected model
- Fallback use
- Auto to Tier fallback
- Provider errors
- Provider recovery
- Probe results
- Cost estimate
- Actual API cost if known
- Equivalent savings

Logs should not include full prompt content unless debug logging is enabled.

---

## 36. Success Criteria

The router is successful when:

- It can route requests without manual model switching.
- It avoids paid APIs when subscription or local models can complete the task.
- It detects provider limits reliably.
- It removes exhausted providers from routing.
- It restores providers after recovery.
- It falls back from Smart Auto Routing to Tier Routing safely.
- It preserves flexible providers such as Copilot when possible.
- It tracks cost savings.
- It improves over time using learning memory.

---

## 37. Example Routing Scenarios

### Scenario 1: GPT Task With Codex and Copilot Available

Task:

```text
Complex Python debugging
```

Available:

```text
Codex GPT-5.4: available
Copilot GPT-5.4: available
Copilot Claude: available
```

Decision:

```text
Use Codex GPT-5.4
```

Reason:

```text
Task requires GPT-class reasoning. Codex is less flexible than Copilot. Preserve Copilot for Claude or Gemini tasks.
```

---

### Scenario 2: Codex Limit Reached

Codex returns:

```text
Weekly usage limit reached. Try again later.
```

Action:

```text
Classify as SUBSCRIPTION_LIMIT.
Remove Codex GPT models from routing.
Use Copilot GPT if available.
Schedule recovery probe.
```

---

### Scenario 3: Smart Routing Fails

Routing LLM unavailable.

Action:

```text
Fall back to Tier Routing.
Classify task as T4.
Use T4 primary model.
Log auto_to_tier_fallback = true.
```

---

### Scenario 4: All Normal GPT Models Unavailable

Available:

```text
Codex GPT: unavailable
Copilot GPT: unavailable
OpenAI API GPT: fallback standby
DeepSeek API: fallback standby
```

Action:

```text
Activate cheapest fallback provider in the equivalent class.
Notify user if paid API confirmation is enabled.
```

---

### Scenario 5: Provider Recovers

Scheduled probe to Codex succeeds.

Action:

```text
Set Codex to AVAILABLE.
Restore Codex GPT models to routing.
Stop probing.
Notify user.
```

---

## 38. Open Questions for Implementation

These must be confirmed during technical design:

1. Exact Hermes plugin interface.
2. Exact Hermes provider discovery method.
3. Whether Hermes exposes OAuth provider model lists directly.
4. Whether provider health can be checked without consuming premium quota.
5. Whether GitHub Copilot exposes quota state in error messages.
6. Whether ChatGPT Codex exposes reset times in error messages.
7. How Hermes executes provider-specific model selection.
8. Whether Workspace can expose the same router config.
9. Whether the router can intercept all Hermes requests or only plugin-routed requests.
10. Whether provider probing should be opt-in by default.

---

## 39. Final Product Summary

Hermes Smart Router is a subscription-aware, provider-aware, and learning-capable model router.

It supports two routing modes:

1. Tier Routing
2. Smart Auto Routing

Smart Auto Routing falls back to Tier Routing if auto routing fails.

The router manages provider availability, detects subscription limits, removes exhausted models, activates fallback providers only when required, and restores providers once they recover.

It accounts for equivalent models across providers and preserves flexible providers such as GitHub Copilot for tasks that need their unique model options.

Phase 2 adds learning memory, cost savings tracking, price syncing, provider phrase learning, quota prediction, and smarter routing over time.

The final result should feel like:

```text
VS Code Copilot Auto Mode for Hermes, with subscription-aware routing, fallback protection, and cost intelligence.
```

---

## 40. Delivery Phases

### Phase 1 - Foundation

- [ ] Define the Hermes backend plugin interface
- [ ] Add the one-command installer and bootstrap flow
- [ ] Implement chat-based runtime notifications
- [ ] Implement the terminal setup and configuration interface
- [ ] Add provider discovery, health checks, and cooldown tracking
- [ ] Implement Tier Routing with primary and fallback models
- [ ] Implement Smart Auto Routing with fallback to Tier Routing
- [ ] Add provider equivalence groups and flexibility scoring
- [ ] Add local storage, config export, and basic cost logging

### Phase 2 - Intelligence

- [ ] Add learning memory for routing decisions
- [ ] Add historical success scoring and similar task lookup
- [ ] Add provider message interpretation improvements
- [ ] Add recovery prediction and scheduled probing improvements
- [ ] Add cost savings reporting and dashboard views
- [ ] Add auto price fetching and cached model pricing
- [ ] Add quota estimation and subscription value tracking

### Phase 3 - Automation and Sharing

- [ ] Add self-tuning routing policies
- [ ] Add benchmark mode and provider capability profiles
- [ ] Add workspace dashboard integration
- [ ] Add exportable analytics reports
- [ ] Add team or community routing profile support
- [ ] Add packaging and release automation for GitHub distribution
- [ ] Add optional shared templates and public model registry support

