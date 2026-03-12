import os
import json
import litellm
import subprocess
import re
from litellm import completion
from litellm.exceptions import RateLimitError, ContextWindowExceededError, APIConnectionError, ServiceUnavailableError, NotFoundError
from pydantic import BaseModel, Field
from typing import TypeVar, Type
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Global Configuration
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gemini/gemini-3-flash-preview"

FALLBACK_MODELS = [
    "gemini/gemini-2.5-flash",       
    "gemini/gemini-2.5-flash-lite", 
    "gemini/gemini-2.5-pro"          
]
_CURRENT_ACTIVE_MODEL = None

load_dotenv()

# Enable client-side schema validation to ensure the LLM respects our rigid structures
litellm.enable_json_schema_validation = True #

# Setup for generic type hinting (so your IDE knows which Pydantic model is returning)
T = TypeVar('T', bound=BaseModel)
# ---------------------------------------------------------------------------
# Global Dual-Loop Router for JSON / API troubleshooting
# ---------------------------------------------------------------------------
def robust_completion(base_model: str, messages: list, response_format: Type[T]) -> T:
    """
    A global router that handles JSON formatting retries locally, 
    but falls back to different API models if Token/Rate limits are hit.
    """
    global _CURRENT_ACTIVE_MODEL
    models_to_try = [base_model] + FALLBACK_MODELS
    max_attempts = 3

    # --- OUTER LOOP: API Fallback Routing ---
    for current_model in models_to_try:
        if current_model != _CURRENT_ACTIVE_MODEL:
            print(f"  🤖 [Model Active] {current_model}")
            _CURRENT_ACTIVE_MODEL = current_model
        # --- INNER LOOP: JSON Retry Logic ---
        for attempt in range(max_attempts):
            try:
                response = completion(
                    model=current_model,
                    max_tokens=4096,
                    temperature=0.0,
                    messages=messages,
                    response_format=response_format,
                )
                return response_format.model_validate_json(response.choices[0].message.content)
                
            except (RateLimitError, ContextWindowExceededError, APIConnectionError) as e:
                print(f"  ⚠️ [API Limit] Rate/Token limit hit on {current_model}. Routing to fallback...")
                break  # Break inner loop, move to the next fallback model

            except (ServiceUnavailableError) as e:
                print(f"  ⚠️ [Server Down] Server issue on {current_model}. Routing to fallback...")
                break  # Break inner loop, move to the next fallback model    

            except (NotFoundError) as e:
                print(f"  Model {current_model} Not Found on LiteLLM. Routing to fallback...")
                break  # Break inner loop, move to the next fallback model

            except Exception as e:
                last_err = e
                print(f"  ⚠️ [Attempt {attempt + 1} Failed] JSON/Formatting error on {current_model}. Retrying...")
                if attempt == max_attempts - 1:
                    print(f"  ❌ Max formatting retries reached on {current_model}.")
                    break  # Crash. Do NOT fallback if the model just can't format JSON.

    raise Exception(f"❌ Pipeline failed, last Error is {last_err}.")


# ---------------------------------------------------------------------------
# 1. Rigid Data Structures (Pydantic)
# These act as the "contracts" between our agents. 
# ---------------------------------------------------------------------------

class PseudocodePlan(BaseModel):
    module_name: str = Field(description="The name of the hardware module.")
    target_compiler: str = Field(description="The target HLS compiler mentioned in the spec (e.g., 'Google XLS', 'Vitis HLS'). If not specified, default to 'Google XLS'.")
    hardware_classification: str = Field(description="Classify as exactly one: 'COMBINATIONAL', 'SEQUENTIAL_PIPELINE', or 'STATE_MACHINE'.")
    inputs_outputs: dict[str, str] = Field(description="Dictionary of signal names and their widths.")
    state_elements: list[str] = Field(description="List any required memory elements, registers, or history arrays. Return empty list if purely combinational.")
    logic_steps: str = Field(description="Step-by-step pseudocode logic.")

class PythonReference(BaseModel):
    python_code: str = Field(description="Executable Python code representing the hardware logic.")
    # test_vectors: list[dict[str, int]] = Field(description="Sample input/output dictionaries for testing.")
    # Commented to avoid JSON formatting errors and token envelope exhaustion

class CppHlsTarget(BaseModel):
    cpp_code: str = Field(description="Synthesizable C++ code ready for HLS.")
    # --- Generalized to avoid triggering Xilinx hallucinations ---
    compiler_directives: str = Field(description="Comma-separated list of compiler-specific directives used, or 'None'.")

class CppCorrection(BaseModel):
    fixed_cpp_code: str = Field(description="The corrected C++ code.")
    explanation: str = Field(description="Brief explanation of what was fixed.")

class CppTestbench(BaseModel):
    testbench_code: str = Field(description="C++ testbench code containing a main() function to validate the module. Use \\n for newlines.")
    test_cases_covered: str = Field(description="A brief comma-separated list of the test scenarios covered.")

# ---------------------------------------------------------------------------
# 2. The Agent Pipeline
# ---------------------------------------------------------------------------

class CirbuildProgressiveCoder:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model = model_name

    def understand_and_plan(self, spec_text: str) -> PseudocodePlan:
        print(f"Step 1: Translating Spec to Pseudocode...")
        
        system_prompt = """
        You are a Senior Hardware Architect. Your job is to extract raw specifications into a rigid architectural plan in pseudocode.
        Ensure logical correctness and clear signal definitions.
        CRITICAL TASKS:
        1. Classify the hardware: Is it purely Combinational (math/logic), a Sequential Pipeline (data flows through stages over multiple clocks), or a State Machine (control logic with distinct states)?
        2. Identify State: Explicitly list any memory, history, or registers required to persist across clock cycles.
        3. Define exact bit-widths for all I/O interfaces.
        """
        
        prompt = f"""
        Hardware Specification:
        {spec_text}
        """
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": prompt.strip()}
        ]
        
        return robust_completion(self.model, messages, PseudocodePlan) 

    def generate_python_gold_model(self, plan: PseudocodePlan) -> PythonReference:
        print("Step 2: Generating Python Reference Model...")
        
        # Notice we are using standard Python f-strings {} here for variable interpolation.
        # Keep $$ syntax strictly for your LaTeX/Markdown docs, not for passing prompt variables!
        prompt = f"""
        Convert this hardware plan into a Python function.
        Module: {plan.module_name}
        I/O: {plan.inputs_outputs}
        Logic: {plan.logic_steps}
        """
        system_prompt = """
        You are a bit-accurate Python hardware modeling expert. Intepret and implement the provided psuedocode plan to functionally and syntatically correct Hardware Python code.
        CRITICAL STRICT RULES: 
        1. DO NOT include ANY comments (# lines) in the output code. Provide ONLY the raw logic. 
        2. BIT-ACCURACY: You MUST emulate hardware bit-widths using bitwise masking (e.g., `val & 0xFF` for 8-bit, `val & 0xFFFF` for 16-bit) after EVERY mathematical operation to perfectly simulate hardware overflow and truncation.
        3. You MUST strictly adhere to the exact signal names, bit-widths, and data types (signed vs unsigned) specified in the inputs/outputs dictionary.
        4. IMPORTANT: You are outputting into a JSON string. You must properly escape all newlines as \\n and avoid using double quotes inside the code (use single quotes instead).
        """
        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": prompt.strip()}
        ]
        
        return robust_completion(self.model, messages, PythonReference)

    def generate_hls_cpp(self, py_model: PythonReference, target_compiler: str) -> CppHlsTarget:
        print(f"Step 3: Translating Python to Synthesizable C++ for [{target_compiler}]...")

        universal_hls_rules = """
        [UNIVERSAL HLS CONSTRAINTS - APPLY TO ALL COMPILERS]
        1. NO DYNAMIC MEMORY: You are writing physical silicon. DO NOT use `new`, `malloc`, `std::vector`, or pointers for dynamic allocation. All arrays must have statically known, fixed sizes at compile time.
        2. STATE ENCAPSULATION: All internal registers, memory, and history must be encapsulated within a `struct` or `class`.
        3. BIT-ACCURATE TYPES: Use exact-width native types (e.g., `unsigned char`, `unsigned short`). 
        """
        compiler_rules = {
            "google xls": f"""
                {universal_hls_rules}
                1. DO NOT use Xilinx Vitis HLS libraries. NO #include "ap_int.h". NO ap_uint.
                2. DO NOT use Xilinx pragmas. NO #pragma HLS INTERFACE.
                3. COMPILER SPECIFIC: Use exactly one `#pragma hls_top` before the top-level evaluation function.
                4. NO SYSTEM HEADERS: DO NOT use ANY #include directives (NO #include <cstdint>). The compiler environment is stripped. 
                5. Use native C++ built-in types instead of stdint: use `unsigned char` for 8-bit, `unsigned short` for 16-bit, `unsigned int` for 32-bit, and `bool`.
                6. Always include an explicit active-low reset signal (e.g., rst_n) in the top-level evaluation function parameters and use if (!rst_n) to clear internal states.
                7. LOOP PRAGMAS: If the hardware is COMBINATIONAL or computing datapath math within a single clock cycle, you MUST precede the `for` loop with `#pragma hls_unroll yes`. If the loop represents a sequential process that takes multiple clock cycles, DO NOT unroll it.
                8. PASS BY REFERENCE: Pass the state struct by reference into the top-level function.
            """,
            "vitis hls": f"""
                {universal_hls_rules}
                1. Use standard Xilinx Vitis HLS libraries. You MUST #include "ap_int.h" and use ap_uint/ap_int types.
                2. Apply appropriate #pragma HLS INTERFACE and #pragma HLS PIPELINE directives.
                3. Use strictly standard C++ libraries like <cstdint> (e.g., uint8_t, uint16_t, bool).
            """
        }
        
        selected_rules = compiler_rules["vitis hls"] if "vitis" in target_compiler.lower() else compiler_rules["google xls"]

        system_prompt = f"""
        You are an expert hardware compiler engineer targeting {target_compiler}. 
        Translate the provided Python reference model into synthesizable C++.
        
        CRITICAL STRICT RULES:
        {selected_rules}
        - DO NOT include ANY comments (// or /*) in the output code. Provide ONLY the raw logic.
        - IMPORTANT: Output into a JSON string. Escape newlines as \\n and use single quotes inside the code.
        - You MUST strictly adhere to the exact signal names, bit-widths, and data types (signed vs unsigned) specified in the inputs/outputs dictionary.
        - Always encapsulate module state (registers/arrays) inside a C++ class or struct. DO NOT use global or static variables for hardware state.
        - Use C++ templates (e.g., template <int N>) and generic for loops for scalable logic rather than hardcoding arrays and manually unrolling shift registers.
        - "HEADER GUARDS: You MUST wrap the entire C++ code in standard include guards (e.g., `#ifndef MODULE_NAME_H`, `#define MODULE_NAME_H`, ... `#endif`) to prevent duplicate definitions during testbench compilation."
        """
        
        prompt = f"""
        Python Code:
        {py_model.python_code}
        """
        
        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": prompt.strip()}
        ]
        
        return robust_completion(self.model, messages, CppHlsTarget)
    def patch_xls_headers(self, cpp_code: str) -> str:
        """
        Hardcodes a bypass for the missing <cstdint> library in Google XLS 
        by injecting standard typedefs directly into the file.
        """
        # 1. Deterministically strip the problematic standard headers
        cpp_code = cpp_code.replace("#include <cstdint>", "")
        cpp_code = cpp_code.replace("#include <stdint.h>", "")
    
       # 2. Safely replace exact whole words (using \b boundaries)
       # This prevents accidentally replacing variables like "my_uint8_t_val"
        replacements = {
        r'\buint8_t\b': 'unsigned char',
        r'\buint16_t\b': 'unsigned short',
        r'\buint32_t\b': 'unsigned int',
        r'\buint64_t\b': 'unsigned long long',
        r'\bint8_t\b': 'signed char',
        r'\bint16_t\b': 'short',
        r'\bint32_t\b': 'int',
        r'\bint64_t\b': 'long long'
        }
        for pattern, native_type in replacements.items():
            cpp_code = re.sub(pattern, native_type, cpp_code)
        
        return cpp_code.strip()
        
    
    
class CirbuildReflectionAgent:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model = model_name
    
    def mock_compile_check(self, filename: str) -> str:
        """
        In a real lab environment, this would call your HLS compiler (e.g., Vitis HLS).
        For testing the loop, we use standard g++ to check basic C++ syntax.
        (Note: g++ will complain about ap_int.h unless you have the headers in your path, 
        but we can use this structure to capture any stderr output).
        """
        print(f"Running syntax check on {filename}...")
        try:
            # -fsyntax-only checks for code errors without trying to link a full executable
            result = subprocess.run(
                ["g++", "-fsyntax-only", filename],
                capture_output=True,
                text=True,
                check=True
            )
            return "SUCCESS"
        except subprocess.CalledProcessError as e:
            # Return the exact compiler error message
            return e.stderr

    def run_full_xls_pipeline(self, cpp_filename: str, docker_image: str = "cirbuild-xls:v1"):
        print(f"\n⚙️ Phase 5: Executing Full Google XLS Compilation Pipeline...")
        
        # Define the file progression
        ir_file = cpp_filename.replace(".cpp", ".ir")
        opt_ir_file = cpp_filename.replace(".cpp", ".opt.ir")
        v_file = cpp_filename.replace(".cpp", ".v")
        
        local_dir = os.getcwd()
        
        # The base command spins up the pre-built image in milliseconds
        base_docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{local_dir}:/workspace",
            "-w", "/workspace",
            docker_image
        ]
        
        try:
            # ---------------------------------------------------------
            # Step 1: C++ to XLS IR (xlscc)
            # ---------------------------------------------------------
            print("   -> Step 1: Converting C++ to XLS IR...")
            xlscc_cmd = base_docker_cmd + ["/home/xls-developer/.cache/bazel/_bazel_xls-developer/970c5c2433bb6038ab152477a024c421/execroot/_main/bazel-out/k8-opt/bin/xls/contrib/xlscc/xlscc", cpp_filename]
            xlscc_process = subprocess.run(xlscc_cmd, check=True, capture_output=True, text=True)
            with open(ir_file, "w") as f:
                f.write(xlscc_process.stdout)
            
            # ---------------------------------------------------------
            # Step 2: Optimize the IR (opt_main)
            # ---------------------------------------------------------
            print("   -> Step 2: Optimizing IR...")
            opt_cmd = base_docker_cmd + ["/home/xls-developer/.cache/bazel/_bazel_xls-developer/970c5c2433bb6038ab152477a024c421/execroot/_main/bazel-out/k8-opt/bin/xls/tools/opt_main", ir_file]
            
            # opt_main outputs to stdout, so we capture it and write to file
            opt_process = subprocess.run(opt_cmd, check=True, capture_output=True, text=True)
            with open(opt_ir_file, "w") as f:
                f.write(opt_process.stdout)

            # ---------------------------------------------------------
            # Step 3: Generate Verilog (codegen_main)
            # ---------------------------------------------------------
            print("   -> Step 3: Generating Synthesizable Verilog...")
            codegen_cmd = base_docker_cmd + [
                "/home/xls-developer/.cache/bazel/_bazel_xls-developer/970c5c2433bb6038ab152477a024c421/execroot/_main/bazel-out/k8-opt/bin/xls/tools/codegen_main", opt_ir_file,
                "--generator", "combinational"
            ]
            
            # codegen_main also outputs to stdout
            codegen_process = subprocess.run(codegen_cmd, check=True, capture_output=True, text=True)
            with open(v_file, "w") as f:
                f.write(codegen_process.stdout)

            print(f"✅ Pipeline Complete! Verilog saved to: {v_file}")
            return True, v_file

        except subprocess.CalledProcessError as e:
            print(f"❌ XLS Compilation Failed at step: {' '.join(e.cmd)}")
            print(f"Error Log:\n{e.stderr}")
            return False, e.stderr

    def fix_compilation_error(self, bad_code: str, error_log: str, target_compiler: str) -> CppCorrection:
        print(f"Reflection Agent triggered: Analyzing compiler errors for [{target_compiler}]...")
        
        compiler_rules = {
            "google xls": """
                1. DO NOT use Xilinx Vitis HLS libraries. NO #include "ap_int.h". NO ap_uint.
                2. DO NOT use Xilinx pragmas. NO #pragma HLS INTERFACE.
                3. For Google XLS, you MUST use exactly one top-level pragma: `#pragma hls_top` placed immediately before the top-level evaluation function.
                4. DO NOT use ANY #include directives (NO #include <cstdint>). The compiler environment is stripped. 
                5. Use native C++ built-in types instead of stdint: use `unsigned char` for 8-bit, `unsigned short` for 16-bit, `unsigned int` for 32-bit, and `bool`.
                6. Always include an explicit active-low reset signal (e.g., rst_n) in the top-level evaluation function parameters and use if (!rst_n) to clear internal states.
                7. LOOP UNROLLING: Every single `for` loop MUST be immediately preceded by `#pragma hls_unroll yes` to ensure it is synthesized as combinational logic. 
            """,
            "vitis hls": """
                1. Use standard Xilinx Vitis HLS libraries. You MUST #include "ap_int.h" and use ap_uint/ap_int types.
                2. Apply appropriate #pragma HLS INTERFACE and #pragma HLS PIPELINE directives.
                3. Use strictly standard C++ libraries like <cstdint> (e.g., uint8_t, uint16_t, bool).
            """
        }
        
        selected_rules = compiler_rules["vitis hls"] if "vitis" in target_compiler.lower() else compiler_rules["google xls"]

        system_prompt = f"""
        You are an expert {target_compiler} C++ debugging agent. 
        
        CRITICAL STRICT RULES:
        {selected_rules}
        - DO NOT include ANY comments. Provide ONLY the raw logic.
        - IMPORTANT: Output as a JSON string. Escape newlines as \\n and use single quotes in the code.
        """

        prompt = f"""
        The following C++ HLS code failed to compile.
        
        [CODE]
        {bad_code}
        
        [COMPILER ERROR LOG]
        {error_log}
        
        Fix the errors and provide the corrected C++ code. Keep it clean and synthesizable.
        """

        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": prompt.strip()}
        ]
        
        return robust_completion(self.model, messages, CppCorrection)

class CirbuildVerifierAgent:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model = model_name

    def generate_cpp_testbench(self, plan: PseudocodePlan, target_compiler: str, generated_cpp: str) -> CppTestbench:
        print(f"Step 4: Generating C++ Testbench for [{target_compiler}]...")
        
        compiler_rules = {
            "google xls": """
                1. Use standard C++ types (<cstdint>). DO NOT use Xilinx ap_int.h.
                2. Assume the module uses an active-low reset (rst_n) if it requires reset logic.
            """,
            "vitis hls": """
                1. Use Xilinx Vitis HLS libraries (#include "ap_int.h").
            """
        }
        
        selected_rules = compiler_rules["vitis hls"] if "vitis" in target_compiler.lower() else compiler_rules["google xls"]

        system_prompt = f"""
        You are an expert hardware verification engineer targeting {target_compiler}.
        Write a C++ testbench for the described hardware module.
        
        CRITICAL STRICT RULES:
        {selected_rules}

        [HARDWARE INTEGRATION]
        - The hardware module is ALREADY included via '#include "{output_filename}"'.
        - CRITICAL: DO NOT add any other local #include directives (e.g., NO #include "fir_filter.h").
        - All necessary structs (like FirState) and functions are already available from the primary include. 
        - Do not redefine any hardware logic, classes, or structs.
        - ONLY include standard libraries (<iostream>, <deque>, etc.).

        [TESTING STRATEGY]
        - Write ALGORITHMIC testbenches (use `for` loops, boundary checks, edge-case generation). Avoid unrolled, brute-force assert lines.
        - DYNAMIC ASSERTIONS: Compute expected values dynamically at runtime using a software shadow-state (e.g., std::deque). Do not hardcode expected output arrays.
        - STATE SYNCHRONIZATION: If you assert a hardware reset (!rst_n), you MUST simultaneously clear your shadow-state variables to match.
        - Always use loops for shift register propagation.

        [FORMATTING & OUTPUT]
        - Write ONLY the `int main()` function and necessary standard includes.
        - Provide ONLY raw C++ logic. Zero comments (// or /*) are allowed.
        - Success/Failure: Print "TEST PASSED" and return 0 on success. Return 1 on failure.
        - JSON FORMAT: Output as a valid JSON string. Use standard C++ double quotes for literals (e.g., "TEST PASSED") and escape them properly for JSON.
        """
        
        prompt = f"""
        Module Name: {plan.module_name}
        I/O Interface: {plan.inputs_outputs}
        Expected Behavior: {plan.logic_steps}

        Generated C++ Hardware Module (Already Included in environment):
        {generated_cpp}

        [STRUCTURAL TEMPLATE FOR TESTBENCH]
        You MUST follow this exact architectural skeleton, but replace the generic types, functions, and logic with the specific requirements of the module described above:

        ```cpp
        #include <iostream>
        #include <cassert>
        // Include any required data structures for the shadow state (e.g., <deque>, <vector>)
        #include "module.cpp"

        int main() {{
            // 1. Initialize Software Shadow State
            <ShadowStateType> shadow_state; 
            
            // 2. Hardware Reset & Shadow State Synchronization
            <module_function_name>(<zero_inputs>, false, ...); 
            // IMMEDIATELY reset the shadow state to match!
            shadow_state.clear(); // (or equivalent reset logic)

            // 3. Algorithmic Test Loop (Edge cases, sweeps, or randoms)
            for (int i = 0; i < <NUM_TESTS>; ++i) {{
                // a. Generate bounded dynamic test inputs (e.g., modulo the max bit-width)
                // b. Update software shadow state
                // c. Compute expected output dynamically from the shadow state
                // d. Evaluate hardware and assert
                if (hw_out != expected_out) {{
                    return 1;
                }}
            }}
            
            std::cout << "TEST PASSED" << std::endl;
            return 0;
        }}
        ```
        """
        
        messages=[
             {"role": "system", "content": system_prompt.strip()},
             {"role": "user", "content": prompt.strip()}
        ]
        return robust_completion(self.model, messages, CppTestbench)
# ---------------------------------------------------------------------------
# 3. Execution Block
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_spec = """
    Module Name: 4-Tap Moving Average Filter
    Target Compiler: Google XLS
    
    Description:
    Design a 4-tap moving average filter.
    
    I/O Interface:
    - Input: 8-bit unsigned integer named 'data_in'
    - Output: 8-bit unsigned integer named 'data_out'
    
    Timing & Logic:
    - The filter updates every single clock cycle.
    - It calculates the average of the last 4 inputs.
    """

    planner_agent = CirbuildProgressiveCoder(model_name="gemini/gemini-2.5-flash")
    coder_agent = CirbuildProgressiveCoder(model_name=DEFAULT_MODEL)
    reflection_agent = CirbuildReflectionAgent(model_name=DEFAULT_MODEL)
    verifier_agent = CirbuildVerifierAgent(model_name=DEFAULT_MODEL) 
    
    try:
        # ---------------------------------------------------------
        # Phase 1: Core Generation
        # ---------------------------------------------------------
        plan = planner_agent.understand_and_plan(sample_spec)
        py_model = coder_agent.generate_python_gold_model(plan)
        cpp_target = coder_agent.generate_hls_cpp(py_model, plan.target_compiler)

        final_cpp_code = cpp_target.cpp_code
        if "google xls" in plan.target_compiler.lower():
            final_cpp_code = coder_agent.patch_xls_headers(final_cpp_code)
        
        safe_name = plan.module_name.strip().lower().replace(" ", "_").replace("-", "_")
        output_filename = f"{safe_name}_hls.cpp"
        
        with open(output_filename, "w") as file:
            file.write(final_cpp_code.replace('\\n', '\n'))
            
        print(f"\n✅ Phase 1: Initial C++ Code Saved to {output_filename}")

        # ---------------------------------------------------------
        # Phase 2: Core Syntax Check & Reflection
        # ---------------------------------------------------------
        compile_status = reflection_agent.mock_compile_check(output_filename)
        
        if compile_status != "SUCCESS":
            print(f"\n❌ Phase 2: Core Compilation Failed. Passing to Reflection Agent...\nError:\n{compile_status}")
            
            correction = reflection_agent.fix_compilation_error(cpp_target.cpp_code, compile_status, plan.target_compiler)
            
            with open(output_filename, "w") as file:
                file.write(correction.fixed_cpp_code.replace('\\n', '\n'))
                
            print(f"\n🔧 Code Fixed! Explanation: {correction.explanation}")
        else:
            print("\n✅ Phase 2: Core C++ passed syntax check on the first try!")

        # ---------------------------------------------------------
        # Phase 3: Testbench Generation
        # ---------------------------------------------------------
        
        cpp_tb = verifier_agent.generate_cpp_testbench(plan, plan.target_compiler, cpp_target.cpp_code)
        
        tb_filename = f"{safe_name}_tb.cpp"
        with open(tb_filename, "w") as file:
            include_statement = f'#include "{output_filename}"\n\n'
            file.write(include_statement + cpp_tb.testbench_code.replace('\\n', '\n'))
            
        print(f"\n✅ Phase 3: C++ Testbench Saved to {tb_filename}")
        print(f"   Test Scenarios Covered: {cpp_tb.test_cases_covered}")

        # ---------------------------------------------------------
        # Phase 4: Full Compilation & Execution
        # ---------------------------------------------------------
        print(f"\n⚙️ Phase 4: Compiling and Executing Testbench in WSL...")
        executable_name = f"./{safe_name}_tb_exec"

        try:
            # 1. Compile the testbench (which includes the core code)
            subprocess.run(
                ["g++", tb_filename, "-o", executable_name],
                capture_output=True,
                text=True,
                check=True 
            )
            print("✅ Compilation Successful.")

            # 2. Run the compiled executable
            run_process = subprocess.run(
                [executable_name],
                capture_output=True,
                text=True,
                check=True 
            )

            print("\n📊 Testbench Output:")
            print(run_process.stdout.strip())

            # 3. Verify the output
            if "TEST PASSED" in run_process.stdout:
                print("\n🏆 VERIFICATION SUCCESSFUL: The hardware logic is functionally correct!")
                # ---------------------------------------------------------
                # Phase 5: Full HLS to Verilog Pipeline
                # ---------------------------------------------------------
                # Note: Replace 'your_xls_image_name' with your actual local Docker image tag
                success, output_info = reflection_agent.run_full_xls_pipeline(
                    cpp_filename=output_filename, 
                    docker_image="cirbuild-xls:v1" 
                )
            
                if success:
                    print(f"\n🎉 EDA Pipeline Complete! Ready for FPGA synthesis.")
                    print(f"📄 Final RTL: {output_info}")
                else:
                    print(f"\n❌ XLS Compiler Pipeline Failed:\n{output_info}")
            else:
                print("\n❌ VERIFICATION FAILED: The logic did not produce the expected outputs.")

        except subprocess.CalledProcessError as e:
            print(f"\n❌ Pipeline Execution Failed.")
            if e.cmd[0] == 'g++':
                print(f"Testbench Compiler Error Log:\n{e.stderr}")
            else:
                print(f"Runtime/Assertion Error Log:\n{e.stderr}")

    except Exception as e:
        print(f"\nPipeline critical failure: {e}")
