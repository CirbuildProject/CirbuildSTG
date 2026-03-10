import os
import json
import litellm
import subprocess
from litellm import completion
from litellm.exceptions import RateLimitError, ContextWindowExceededError, APIConnectionError
from pydantic import BaseModel, Field
from typing import TypeVar, Type
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Global Configuration
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gemini/gemini-2.5-flash"

FALLBACK_MODELS = [
     "groq/llama3-8b-8192", 
     "openai/gpt-4o-mini"
 ]

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
    models_to_try = [base_model] + FALLBACK_MODELS
    max_attempts = 3

    # --- OUTER LOOP: API Fallback Routing ---
    for current_model in models_to_try:
        
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
                
            except Exception as e:
                print(f"  ⚠️ [Attempt {attempt + 1} Failed] JSON/Formatting error on {current_model}. Retrying...")
                if attempt == max_attempts - 1:
                    print(f"  ❌ Max formatting retries reached on {current_model}.")
                    raise e  # Crash. Do NOT fallback if the model just can't format JSON.

    raise Exception("❌ All API fallback models exhausted due to Token/Network limits.")


# ---------------------------------------------------------------------------
# 1. Rigid Data Structures (Pydantic)
# These act as the "contracts" between our agents. 
# ---------------------------------------------------------------------------

class PseudocodePlan(BaseModel):
    module_name: str = Field(description="The name of the hardware module.")
    target_compiler: str = Field(description="The target HLS compiler mentioned in the spec (e.g., 'Google XLS', 'Vitis HLS'). If not specified, default to 'Google XLS'.")
    inputs_outputs: dict[str, str] = Field(description="Dictionary of signal names and their widths.")
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
        print(f"Step 1: Translating Spec to Pseudocode using {self.model}...")
        
        system_prompt = """
        You are an expert hardware architect. Extract the specification into a rigid pseudocode plan. 
        Ensure logical correctness and clear signal definitions.
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
        You are a Python hardware modeling expert. Intepret and implement the provided psuedocode plan to functionally and syntatically correct Hardware Python code.
        CRITICAL STRICT RULES: 
        1. DO NOT include ANY comments (# lines) in the output code. Provide ONLY the raw logic. 
        2. IMPORTANT: You are outputting into a JSON string. You must properly escape all newlines as \\n and avoid using double quotes inside the code (use single quotes instead).
        """
        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": prompt.strip()}
        ]
        
        return robust_completion(self.model, messages, PythonReference)

    def generate_hls_cpp(self, py_model: PythonReference, target_compiler: str) -> CppHlsTarget:
        print(f"Step 3: Translating Python to Synthesizable C++ for [{target_compiler}]...")
        
        compiler_rules = {
            "google xls": """
                1. DO NOT use Xilinx Vitis HLS libraries. NO #include "ap_int.h". NO ap_uint.
                2. DO NOT use Xilinx pragmas. NO #pragma HLS INTERFACE.
                3. For Google XLS, you MUST use exactly one pragma: `#pragma hls_top` placed immediately before the top-level evaluation function.
                4. Use strictly standard C++ libraries like <cstdint> (e.g., uint8_t, uint16_t, bool).
                5. Always include an explicit active-low reset signal (e.g., rst_n) in the top-level evaluation function parameters and use if (!rst_n) to clear internal states.
            """,
            "vitis hls": """
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

    def fix_compilation_error(self, bad_code: str, error_log: str, target_compiler: str) -> CppCorrection:
        print(f"Reflection Agent triggered: Analyzing compiler errors for [{target_compiler}]...")
        
        compiler_rules = {
            "google xls": """
                1. DO NOT use Xilinx Vitis HLS libraries (NO ap_int.h). Use standard <cstdint>.
                2. IMPORTANT: You MUST use exactly one pragma: `#pragma hls_top` before the top-level function.
            """,
            "vitis hls": """
                1. Use standard Xilinx Vitis HLS libraries. You MUST #include "ap_int.h" and use ap_uint/ap_int types.
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

    def generate_cpp_testbench(self, plan: PseudocodePlan, target_compiler: str) -> CppTestbench:
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
        - The testbench MUST include a main() function.
        - Instantiate the module, feed it sequential test vectors, and use standard assert() or if-statements to verify the expected outputs.
        - DO NOT write unrolled, brute-force testbenches (e.g., dozens of manual assert lines). 
        - Instead, write ALGORITHMIC testbenches. Use `for` loops, mathematical boundary checks, and programmatic edge-case generation 
          (e.g., testing max/min input values, overflow limits, and reset recovery) to achieve high test coverage with minimal lines of C++ code.
        - If all tests pass, print "TEST PASSED" and return 0. If they fail, return 1.
        - DO NOT include ANY comments (// or /*) in the output code. Provide ONLY the raw C++ logic.
        - IMPORTANT: Output into a JSON string. Escape newlines as \\n and use single quotes inside the code.
        """
        
        prompt = f"""
        Module Name: {plan.module_name}
        I/O Interface: {plan.inputs_outputs}
        Expected Behavior: {plan.logic_steps}
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
    coder_agent = CirbuildProgressiveCoder(model_name=DEFAULT_MODEL)
    reflection_agent = CirbuildReflectionAgent(model_name=DEFAULT_MODEL)
    verifier_agent = CirbuildVerifierAgent(model_name=DEFAULT_MODEL) 
    
    try:
        # ---------------------------------------------------------
        # Phase 1: Core Generation
        # ---------------------------------------------------------
        plan = coder_agent.understand_and_plan(sample_spec)
        py_model = coder_agent.generate_python_gold_model(plan)
        cpp_target = coder_agent.generate_hls_cpp(py_model, plan.target_compiler)
        
        safe_name = plan.module_name.strip().lower().replace(" ", "_").replace("-", "_")
        output_filename = f"{safe_name}_hls.cpp"
        
        with open(output_filename, "w") as file:
            file.write(cpp_target.cpp_code.replace('\\n', '\n'))
            
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
        cpp_tb = verifier_agent.generate_cpp_testbench(plan, plan.target_compiler)
        
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
