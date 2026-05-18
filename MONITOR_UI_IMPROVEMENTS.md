# Hermes Smart Router - Monitor UI Improvements

## Overview

The monitor tool has been completely redesigned with an interactive menu-driven interface for better debugging and visualization of router decisions.

## Key Features

### 1. **Clean Screen on New Prompts**
- Each new routing decision clears the screen
- Shows only the latest routing information
- Eliminates clutter from previous decisions

### 2. **Formatted Decision Display**
The routing decision is displayed in a clean boxed layout:
```
╭──────────────────────────────────────────────────────────────────────────────╮
│                    ⚙ HERMES SMART ROUTER DECISION                           │
├──────────────────────────────────────────────────────────────────────────────┤
│ Prompt: hi what llm are you?                                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│ Selected: codex/gpt-5-mini                                                   │
│ Fallback: copilot/gpt-5.4                                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Mode/Tier/Confidence: smart_auto / T1 / 90%                                  │
│ Estimated Cost: $0.0                                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ Reason: Smart auto routing selected the cheapest competent model...         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### 3. **Interactive Menu System**

After each routing decision, an interactive menu appears with 5 options:

```
╭────────────────────────────────────────────────╮
│                     MENU                       │
├────────────────────────────────────────────────┤
│ 1. View Full Prompt                            │
│ 2. View Routing Reasoning (Logs)               │
│ 3. View Available Models & Providers           │
│ 4. View Router Configuration                   │
│ 5. Back to Monitor                             │
╰────────────────────────────────────────────────╯
```

### 4. **Menu Options**

#### **Option 1: View Full Prompt**
Displays the complete prompt text sent to the router, including:
- User message
- Conversation context
- System variables
- Any other context captured by the hook

#### **Option 2: View Routing Reasoning (Logs)**
Shows:
- The router's decision reasoning
- Confidence calculation details
- Tier matching information
- Relevant debugging logs from the routing hooks

#### **Option 3: View Available Models & Providers**
Displays:
- All configured providers and their status (ENABLED/DISABLED)
- Current tier configuration
- Available models per tier
- Provider aliases and equivalencies

#### **Option 4: View Router Configuration**
Shows current router settings:
- Routing mode (smart_auto, tier-based, etc.)
- Confidence threshold
- Fallback behavior settings
- Provider preservation policy
- Cost tracking status
- History retention period

#### **Option 5: Back to Monitor**
Returns to the main monitor loop waiting for new routing decisions.

## Usage

### Start the Monitor in Follow Mode (Recommended)

```bash
cd /home/kris/.hermes/hermes-agent/plugins/model-providers/ai-gateway/Hermes-Smart-Router
.venv/bin/python -m hermes_plugin_starter monitor --follow --interval 2
```

### Command-Line Options

- `--follow`: Continuously watch for new routing decisions (recommended)
- `--interval SECONDS`: Polling interval in seconds (default: 2.0)
- `--limit N`: Number of historical runs to show (default: 20)
- `--full-prompt`: Display complete prompt text instead of preview
- `--config PATH`: Custom config file path

### Examples

```bash
# Monitor with 1-second polling
.venv/bin/python -m hermes_plugin_starter monitor --follow --interval 1

# View historical runs only (non-interactive)
.venv/bin/python -m hermes_plugin_starter monitor --limit 50 --full-prompt
```

## Debugging Workflow

### Typical Debug Session

1. **Start monitor in follow mode**
   ```bash
   .venv/bin/python -m hermes_plugin_starter monitor --follow
   ```

2. **Open another terminal and trigger a routing decision**
   ```bash
   hermes -z "test prompt for router"
   ```

3. **In monitor terminal, a new decision appears**
   - Clean screen shows the routing box
   - Menu appears automatically

4. **Investigate the decision**
   - Press `2` to see routing reasoning
   - Press `3` to check available models
   - Press `4` to review settings
   - Press `1` to see full prompt context

5. **Return to monitor** by pressing `5`
   - Monitor waits for next decision
   - Repeat as needed

### Common Issues to Debug

#### "Router selecting expensive models unnecessarily"
- Press `3` to verify available models
- Check if confidence threshold is too low (Menu → `4`)
- Review router reasoning for the decision (Menu → `2`)

#### "Fallback model not available"
- Press `2` to see detailed reasoning
- Check `3` to see what models are actually available
- Verify Hermes provider/model discovery is working

#### "Provider preference not respected"
- Press `2` for routing reasoning
- Check `4` for provider preservation settings
- Review how providers are aliased (codex vs openai-codex)

## Implementation Details

### Files Modified

- `src/hermes_plugin_starter/cli.py`: Complete monitor UI rewrite

### New Functions

- `_clear_screen()`: Platform-independent screen clearing
- `_format_box_line()`: Box UI formatting utility
- `_print_routing_decision()`: Main decision display box
- `_show_menu()`: Interactive menu presenter
- `_show_full_prompt()`: Full prompt details view
- `_show_reasoning()`: Routing reasoning view
- `_show_available_models()`: Provider/model catalog view
- `_show_settings()`: Router configuration view
- `_print_monitor_view()`: Historical view (non-interactive)

### Design Principles

1. **Clean on New Input**: Each routing decision starts fresh
2. **Menu-Driven Navigation**: No need to memorize commands
3. **Box UI**: Visual structure using Unicode box drawing
4. **Self-Contained Debugging**: All debug info accessible without leaving monitor
5. **Flexible Views**: Different views for different debugging needs

## Future Enhancements

Potential improvements for later:

- [ ] Real-time metric charts (cost per provider, success rate, etc.)
- [ ] Search/filter historical decisions by provider, model, or confidence
- [ ] Export routing decisions to CSV/JSON
- [ ] Live confidence threshold adjustment
- [ ] Provider enable/disable from monitor
- [ ] Rollback to previous routing configuration
- [ ] A/B testing different tier configurations
