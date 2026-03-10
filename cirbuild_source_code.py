import os
import json
import litellm
import subprocess
from litellm import completion
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Enable client-side schema validation to ensure the LLM respects our rigid structures
litellm.enable_json_schema_validation = True #

# Set your API keys here depending on which model you want to test first
# os.environ["OPENAI_API_KEY"] = "your_openai_key"


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

# ---------------------------------------------------------------------------
# 2. The Agent Pipeline
# ---------------------------------------------------------------------------

class CirbuildProgressiveCoder:
    def __init__(self, model_name: str = "gemini/gemini-2.5-flash"):
        self.model = model_name

    def understand_and_plan(self, spec_text: str) -> PseudocodePlan:
        print(f"Step 1: Translating Spec to Pseudocode using {self.model}...")
        
        response = completion(
            model=self.model,
            max_tokens=4096,
            temperature=0.0,
            messages=[
                {"role": "system", "content": "You are an expert hardware architect. Extract the specification into a rigid pseudocode plan. Ensure logical correctness."},
                {"role": "user", "content": f"Hardware Specification:\n{spec_text}"}
            ],
            response_format=PseudocodePlan, # Forces the LLM to return this exact schema
        )
        return PseudocodePlan.model_validate_json(response.choices[0].message.content)

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
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = completion(
                    model=self.model,
                    max_tokens=4096,
                    temperature=0.0,
                    messages=[
                        {
                            "role": "system", 
                            "content": system_prompt.strip()
                        },
                        {"role": "user", "content": prompt}
                    ],
                    response_format=PythonReference,
                )
                # If this succeeds, it breaks the loop and returns the data
                return PythonReference.model_validate_json(response.choices[0].message.content)
                
            except Exception as e:
                print(f"  [Attempt {attempt + 1} Failed] JSON formatting error caught. Retrying...")
                if attempt == max_attempts - 1:
                    print("  Max retries reached. Pipeline critical failure.")
                    raise e # Give up if it fails max_attempts times in a row

    def generate_hls_cpp(self, py_model: PythonReference, target_compiler: str) -> CppHlsTarget:
        print(f"Step 3: Translating Python to Synthesizable C++ for [{target_compiler}]...")
        
        # --- GATED PROMPT ROUTER ---
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
        
        # Select the rules (default to Google XLS if the string doesn't explicitly match Vitis)
        selected_rules = compiler_rules["vitis hls"] if "vitis" in target_compiler.lower() else compiler_rules["google xls"]

        system_prompt = f"""
        You are an expert hardware compiler engineer targeting {target_compiler}. 
        Translate the provided Python reference model into synthesizable C++.
        
        CRITICAL STRICT RULES:
        {selected_rules}
        - DO NOT include ANY comments (// or /*) in the output code. Provide ONLY the raw logic.
        - IMPORTANT: Output into a JSON string. Escape newlines as \\n and use single quotes inside the code.
        """
        
        # ... (rest of the completion call remains the same)
        response = completion(
            model=self.model,
            max_tokens=4096,
            temperature=0.0,
            max_retries=3,
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": f"Python Code:\n{py_model.python_code}"}
            ],
            response_format=CppHlsTarget,
        )
        return CppHlsTarget.model_validate_json(response.choices[0].message.content)
    
class CirbuildReflectionAgent:
    def __init__(self, model_name: str = "google/gemini-2.5-flash"):
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

    def fix_compilation_error(self, bad_code: str, error_log: str) -> CppCorrection:
        print("Reflection Agent triggered: Analyzing compiler errors...")
        
        prompt = f"""
        The following C++ HLS code failed to compile.
        [CODE]
        {bad_code}
        [COMPILER ERROR LOG]
        {error_log}
        Fix the errors and provide the corrected C++ code. Keep it clean and synthesizable.
        """
        system_prompt = """
        You are an expert Google XLS C++ debugging agent. 
        CRITICAL STRICT RULES:
        1. DO NOT use Xilinx Vitis HLS libraries (NO ap_int.h). Use standard <cstdint>.
        2. DO NOT include ANY comments. Provide ONLY the raw logic.
        3. IMPORTANT: Output as a JSON string. Escape newlines as \\n and use single quotes in the code.
        """

        response = completion(
            model=self.model,
            max_tokens=4096,
            temperature=0.0,
            max_retries=3,
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": prompt}
            ],
            response_format=CppCorrection,
        )
        return CppCorrection.model_validate_json(response.choices[0].message.content)
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
    coder_agent = CirbuildProgressiveCoder(model_name="gemini/gemini-2.5-flash")
    reflection_agent = CirbuildReflectionAgent(model_name="gemini/gemini-2.5-flash")
    
    try:
        # Phase 1: Generation
        plan = coder_agent.understand_and_plan(sample_spec)
        py_model = coder_agent.generate_python_gold_model(plan)
        cpp_target = coder_agent.generate_hls_cpp(py_model, plan.target_compiler)

        safe_name = plan.module_name.strip().lower().replace(" ", "_").replace("-", "_")
        
        output_filename = f"{safe_name}_hls.cpp"
        with open(output_filename, "w") as file:
            file.write(cpp_target.cpp_code.replace('\\n', '\n'))
            
        print(f"\n✅ Initial C++ Code Saved to {output_filename}")

        # Phase 2: Reflection
        # (For this to work locally without Vitis, you can manually inject a typo into the file here to test it)
        compile_status = reflection_agent.mock_compile_check(output_filename)
        
        if compile_status != "SUCCESS":
            print(f"\n❌ Compilation Failed. Passing to Reflection Agent...\nError:\n{compile_status}")
            
            correction = reflection_agent.fix_compilation_error(cpp_target.cpp_code, compile_status)
            
            with open(output_filename, "w") as file:
                file.write(correction.fixed_cpp_code)
                
            print(f"\n🔧 Code Fixed! Explanation: {correction.explanation}")
            print("\n--- REVISED C++ HLS CODE ---")
            print(correction.fixed_cpp_code)
        else:
            print("\n✅ Code passed syntax check on the first try!")

    except Exception as e:
        print(f"Pipeline failed: {e}")
