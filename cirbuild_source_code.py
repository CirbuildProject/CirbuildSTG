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
    inputs_outputs: dict[str, str] = Field(description="Dictionary of signal names and their widths.")
    logic_steps: str = Field(description="Step-by-step pseudocode logic.")

class PythonReference(BaseModel):
    python_code: str = Field(description="Executable Python code representing the hardware logic.")
    # test_vectors: list[dict[str, int]] = Field(description="Sample input/output dictionaries for testing.")

class CppHlsTarget(BaseModel):
    cpp_code: str = Field(description="Synthesizable C++ code ready for HLS.")
    pragmas_used: str = Field(description="List of HLS pragmas included in the code.")

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
        
        response = completion(
            model=self.model,
            max_tokens=4096,
            temperature=0.0,
            max_retries=3,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a Python hardware modeling expert. Keep the output Python code clean, avoid frequent commenting unless necessary. IMPORTANT: You are outputting into a JSON string. You must properly escape all newlines as \\n and avoid using double quotes inside the code (use single quotes instead) to prevent breaking the JSON schema."
                },
                {"role": "user", "content": prompt}
            ],
            response_format=PythonReference,
        )
        return PythonReference.model_validate_json(response.choices[0].message.content)

    def generate_hls_cpp(self, py_model: PythonReference) -> CppHlsTarget:
        print("Step 3: Translating Python to Synthesizable C++...")
        
        response = completion(
            model=self.model,
            max_tokens=4096,
            temperature=0.0,
            messages=[
                {"role": "system", "content": "You are a C++ HLS compiler engineer. Translate the provided Python reference into synthesizable C++. Keep the output code clean. CRITICAL STRICT RULE: DO NOT include ANY comments (// or /*) in the output code. Provide ONLY the raw logic."},
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
        response = completion(
            model=self.model,
            max_tokens=4096,
            temperature=0.0,
            max_retries=3,
            messages=[
                {"role": "system", "content": "You are an expert C++ HLS debugging agent."},
                {"role": "user", "content": prompt}
            ],
            response_format=CppCorrection,
        )
        return CppCorrection.model_validate_json(response.choices[0].message.content)
# ---------------------------------------------------------------------------
# 3. Execution Block
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_spec = "Design a 4-tap moving average filter. It takes an 8-bit unsigned integer input 'data_in' and outputs an 8-bit unsigned integer 'data_out'. It updates every clock cycle."
    
    coder_agent = CirbuildProgressiveCoder(model_name="gemini/gemini-2.5-flash")
    reflection_agent = CirbuildReflectionAgent(model_name="gemini/gemini-2.5-flash")
    
    try:
        # Phase 1: Generation
        plan = coder_agent.understand_and_plan(sample_spec)
        py_model = coder_agent.generate_python_gold_model(plan)
        cpp_target = coder_agent.generate_hls_cpp(py_model)

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
