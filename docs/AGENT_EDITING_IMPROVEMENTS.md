# Agent RTL Editing & Tool-Calling Improvements

## Overview
Fixed critical issues with agent tool-calling limits and added comprehensive logging/visibility for RTL editing workflows.

## Issues Fixed

### 1. **Exit Code 2 - Maximum Tool Calling Rounds**
**Problem:**
- Agent had hardcoded limit of `max_tool_rounds = 5`
- Typical workflow needs: read → edit → package → librelane = 4-5 calls
- Any additional optimization or query exceeded limit
- Error: "[Agent reached maximum tool-calling rounds. Please try again.]"

**Solution:**
- ✅ Increased `max_tool_rounds` from 5 → **15**
- Allows complex workflows with multiple edits, queries, and analysis
- Room for 2-3 RTL modifications per workflow

### 2. **No Visibility for RTL Edits**
**Problem:**
- `write_workspace_file` returned minimal info: just `{"success": True, "path": str}`
- No indication that file was being edited
- User couldn't see what changed
- Editing appeared to "disappear" from logs

**Solution:**
- ✅ Added detailed edit tracking:
  ```json
  {
    "success": true,
    "path": "/path/to/file.v",
    "new_lines": 125,
    "status": "EDITING",          // Clear indicator
    "previous_lines": 120,
    "lines_added": 5,
    "lines_removed": 0
  }
  ```
- ✅ Added logger output: `✏️ [EDITING] File 'xyz.v' modified: 125 lines (was 120 lines)`
- ✅ Status field = `"EDITING"` for clear visual tracking

### 3. **No Final RTL Preview Before Librelane**
**Problem:**
- Agent packaged RTL without showing final code
- User had to trust agent didn't break the design
- No chance to review before synthesis
- `package_for_librelane` returned minimal info

**Solution:**
- ✅ Enhanced `package_for_librelane` to:
  - Display final RTL file content for review
  - Show line counts and file structure
  - Include only first 8 + last 8 lines for long files (with middle summary)
  - Add logger: `🎯 [FINAL RTL] file.v: 125 lines | Ready for synthesis`
  - Return `final_rtl` field with display content
  - Set status = `"PACKAGED"`

## Implementation Details

### File Changes

#### **cirbuild/agent/client.py**
```python
# Line 154: BEFORE
max_tool_rounds = 5  # Prevent infinite tool-calling loops

# AFTER
max_tool_rounds = 15  # Allow complex workflows with multiple edits and analysis
```

**System Prompt Enhancement** (lines 52-76):
- Added "TOOL CALLING WORKFLOW" section with clear guidance
- Documented edit workflow: read → analyze → write → package → run
- Explained tool response formats
- Added "EDITING BEST PRACTICES" with specific guidance

#### **cirbuild/agent/tools.py**  

**`handle_read_workspace_file` (lines 467-485)**:
- Returns: `content`, `lines`, `preview` (first 500 chars)
- Added logger: `📖 Reading '{filename}': {lines} lines`
- Provides context for agent analysis

**`handle_write_workspace_file` (lines 475-518)**:
- Returns: `success`, `path`, `new_lines`, `status`, `previous_lines`, `lines_added`, `lines_removed`
- Tracks changes vs previous version
- Logger: `✏️ [EDITING] File modified: X lines (was Y lines)`
- Status field = `"EDITING"` for clear tracking

**`handle_package_for_librelane` (lines 547-630)**:
- Shows final RTL code (first+last 8 lines for long files)
- Returns: `final_rtl`, `status='PACKAGED'`, `files_count`
- Added logger: `🎯 [FINAL RTL] file.v: NNN lines | Ready for synthesis`
- Includes agent_instruction for next steps: `run_librelane_flow('{module_name}')`

## Usage Examples

### Example 1: Simple RTL Edit Workflow
```
User: "Optimize the ALU for timing. Reduce the critical path."

Action 1 (Round 1): read_workspace_file('alu.v')
  ✅ Tool Response: {content: '...', lines: 120, preview: '...'}
  📖 Logging: "📖 Reading 'alu.v': 120 lines"

Action 2 (Round 2): write_workspace_file('alu.v', optimized_rtl)
  ✅ Tool Response: {success: True, new_lines: 125, lines_added: 5, status: 'EDITING'}
  ✏️ Logging: "✏️ [EDITING] File 'alu.v' modified: 125 lines (was 120 lines)"

Action 3 (Round 3): package_for_librelane('alu')
  ✅ Tool Response: {final_rtl: '...RTL preview...', status: 'PACKAGED'}
  🎯 Logging: "🎯 [FINAL RTL] alu.v: 125 lines | Ready for synthesis"

Action 4 (Round 4): run_librelane_flow('alu')
  ✅ Tool Response: {success: True, metrics_stored: {...}}
  ✅ Synthesis complete!
```

### Example 2: Multiple Edits Workflow
```
User: "Make multiple optimizations: 1) Reduce power, 2) Fix timing, 3) Optimize area"

Round 1: read_workspace_file('rtl.v')          ← Check current state
Round 2: write_workspace_file (power opt)      ← EDITING (75→78 lines, +3)
Round 3: read_workspace_file('rtl.v')          ← Verify power changes
Round 4: write_workspace_file (timing opt)     ← EDITING (78→82 lines, +4)
Round 5: read_workspace_file('rtl.v')          ← Verify timing changes
Round 6: write_workspace_file (area opt)       ← EDITING (82→80 lines, -2)
Round 7: package_for_librelane('module')       ← PACKAGED, show final RTL
Round 8: run_librelane_flow('module')          ← Execute synthesis

✅ Completes in 8 rounds (well within 15 limit)
```

## Logging Indicators

### New Logging Format

```
📖 Reading 'file.v': 120 lines
  → Agent is reviewing RTL for analysis

✏️ [EDITING] File 'file.v' modified: 125 lines (was 120 lines). Status: PENDING REVIEW
  → Agent is making modifications (5 lines added)

🎯 [FINAL RTL] file.v: 125 lines | Ready for synthesis
  → Before sending to librelane, showing final code

📦 [PACKAGING] Module 'alu' ready for librelane. Design dir: /path/to/design
  → Ready for physical design flow

Tool-calling round tracking:
  🔄 Tool-calling round 1/15
  📞 Agent made 1 tool call(s) in round 1
  ✅ Tool XXXXX executed successfully
  ✅ Agent returned text response in round 4
```

## Key Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|------------|
| Max Tool Rounds | 5 | 15 | 3x more workspace for complex workflows |
| Edit Visibility | Minimal | Detailed | Status indicators + line tracking |
| RTL Preview | None | Complete | Final code shown before synthesis |
| Edit Tracking | None | Per-file | Lines added/removed + change metrics |
| Logging Clarity | Generic | Rich | [EDITING], [FINAL RTL], [PACKAGING] indicators |

## Testing the Improvements

### Test 1: Complex Edit Workflow
```bash
python -m cirbuild

You> I need to optimize the ALU for timing while keeping area under 10k um². 
     First, let me make a 3-step optimization.
```

Expected: Agent should complete all edits within 15 rounds, showing:
- ✏️ [EDITING] for each modification
- Line count changes for each edit
- 🎯 [FINAL RTL] before packaging
- Clear completion status

### Test 2: Multiple File Edits
```bash
You> Please optimize both alu.v and shifter.v for power consumption.
```

Expected: Agent should:
- Read both files (2 reads)
- Edit both files (2 writes)
- Package both (2 package calls)
- Run synthesis (1 flow call)
- Complete in ~7 rounds (well under 15 limit)

## Error Handling

Exit code 2 with "maximum tool-calling rounds" should no longer occur unless:
1. Agent is stuck in a loop (intentional safety measure)
2. Workflow requires >15 fundamental operations
3. Agent keeps reading/writing same file without progress

### If limit still hit:
```
[Agent reached maximum tool-calling rounds. Please try again.]
```

Solution: Start fresh conversation with more specific request

## Agent System Prompt Updates

The agent now understands:
- Tool-calling workflow and 15-round limit
- Edit workflow: read → analyze → write → package → run
- What each tool returns (status, metrics, previews)
- Best practices for RTL editing
- When to call vs when to summarize

See `system.jinja2` or fallback prompt in `client.py` (lines 52-76)

## Backward Compatibility

✅ All changes are backward compatible:
- Tool signatures unchanged
- Only response fields expanded (additives)
- Existing code continues to work
- Fallback system prompt used if template fails

## Performance Notes

- Line counting: O(n) on content length
- No performance degradation for normal workflows
- Logging does not block execution
- RTL display truncates long files intelligently

## Future Enhancements

1. **Configurable tool rounds**: Allow user to set max_tool_rounds
2. **Edit history**: Display delta between versions
3. **Agent profiling**: Track round usage per workflow type
4. **Selective RTL display**: User can request specific sections
5. **Edit rollback**: Undo previous modification
