# Quick Reference: Agent RTL Editing

## Issue: "Agent reached maximum tool-calling rounds"
- ✅ FIXED: Increased limit from 5 → 15 rounds
- Allows: read + multiple edits + package + librelane in one request

## Logging Indicators (NEW)

### Reading RTL
```
📖 Reading 'file.v': 168 lines
```

### Editing RTL  
```
✏️ [EDITING] File 'file.v' modified: 175 lines (was 168 lines). Status: PENDING REVIEW
  - Lines changed: +7
  - Previous version: saved
```

### Before Sending to Librelane
```
🎯 [FINAL RTL] file.v: 175 lines | Ready for synthesis

--- file.v (175 lines) ---
module top (
  input clk,
  ...
  (first 8 lines shown)
  
... (159 lines middle content) ...

  endmodule
(last 8 lines shown)
```

### Packaging Complete
```
📦 [PACKAGING] Module 'alu' ready for librelane. Design dir: /workspace/alu/librelane_design
```

## Typical Workflow (Now Works!)

```bash
User: "Edit the RTL to optimize for timing, then send to librelane"

Agent (Round 1):  📖 read_workspace_file('alu.v')           → 150 lines
Agent (Round 2):  ✏️ write_workspace_file (with optimizations) → 155 lines (+5)
Agent (Round 3):  📖 read_workspace_file('alu.v')           → Check changes
Agent (Round 4):  📦 package_for_librelane('alu')           → PACKAGED
Agent (Round 5):  🎯 run_librelane_flow('alu')             → Synthesis complete

✅ Total: 5 rounds (was impossible before, now works!)
```

## Tool Responses Now Include

### read_workspace_file()
```json
{
  "filename": "alu.v",
  "content": "...full content...",
  "lines": 150,
  "preview": "...first 500 chars..."
}
```

### write_workspace_file()
```json
{
  "success": true,
  "path": "/workspace/alu/alu.v",
  "new_lines": 155,
  "previous_lines": 150,
  "lines_added": 5,
  "lines_removed": 0,
  "status": "EDITING"
}
```

### package_for_librelane()
```json
{
  "success": true,
  "final_rtl": "...code preview...",
  "files_count": 1,
  "status": "PACKAGED",
  "agent_instruction": "Ready to run librelane..."
}
```

## What Changed

| Aspect | Before | After |
|--------|--------|-------|
| Max tool calls | 5 | 15 |
| Edit visibility | ❌ Hidden | ✅ [EDITING] indicator + metrics |
| Final RTL preview | ❌ None | ✅ Full display before synthesis |
| Edit tracking | ❌ None | ✅ Line counts + change metrics |
| Logging | Generic | 📖 📝 🎯 📦 indicators |

## No More Failures! ✅

### Before:
```
[Agent reached maximum tool-calling rounds. Please try again.]
Exit code: 2
Error: Tool-calling limit hit on simple edit workflow
```

### After:
```
🔄 Tool-calling round 1/15
📞 Agent made 1 tool call(s) in round 1
✏️ [EDITING] File 'alu.v' modified: 155 lines (was 150)
✅ Tool executed successfully
✅ Agent returned text response in round 5
```

## Use Cases That Now Work

✅ "Optimize RTL for timing while keeping area under 10k um²"
✅ "Fix the critical path in the datapath"
✅ "Add pipeline stages to the ALU"
✅ "Reduce power consumption by 30%"
✅ "Multiple concurrent edits: fix timing AND optimize area"
✅ "Review RTL before synthesis and request changes"

## System Prompt Now Includes

The agent understands:
- 15-round workflow limit (not mysterious failure)
- Edit workflow: read → analyze → write → package → run
- Tool response formats and what to expect
- Best practices for RTL editing
- When to verify changes vs move forward

See: `cirbuild/agent/client.py` lines 52-76, or full guide in `AGENT_EDITING_IMPROVEMENTS.md`
