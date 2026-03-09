import os
import json
import litellm
from litellm import completion
from pydantic import BaseModel, Field

# Enable client-side schema validation to ensure the LLM respects our rigid structures
litellm.enable_json_schema_validation = True #

# Set your API keys here depending on which model you want to test first
# os.environ["OPENAI_API_KEY"] = "your_openai_key"
os.environ["GEMINI_API_KEY"] = "AIzaSyAZkv7sZWMvh8--ydENRWwtnNYf2SC09TI"

# ---------------------------------------------------------------------------
# 1. Rigid Data Structures (Pydantic)
# These act as the "contracts" between our agents. 
# ---------------------------------------------------------------------------

class PseudocodePlan(BaseModel):
    module_name: str = Field(description="The name of the hardware module.")
    inputs_outputs: dict[str, str] = Field(description="Dictionary of signal names and their widths.")
    logic_steps: list[str] = Field(description="Step-by-step pseudocode logic.")

class PythonReference(BaseModel):
    python_code: str = Field(description="Executable Python code representing the hardware logic.")
    test_vectors: list[dict[str, int]] = Field(description="Sample input/output dictionaries for testing.")

class CppHlsTarget(BaseModel):
    cpp_code: str = Field(description="Synthesizable C++ code ready for HLS.")
    pragmas_used: list[str] = Field(description="List of HLS pragmas included in the code.")

# ---------------------------------------------------------------------------
# 2. The Agent Pipeline
# ---------------------------------------------------------------------------

class CirbuildProgressiveCoder:
    def __init__(self, model_name: str = "google/gemini-2.5-flash"):
        self.model = model_name

    def understand_and_plan(self, spec_text: str) -> PseudocodePlan:
        print(f"Step 1: Translating Spec to Pseudocode using {self.model}...")
        
        response = completion(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are an expert hardware architect. Extract the specification into a rigid pseudocode plan."},
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
            messages=[
                {
                    "role": "system", 
                    "content": "You are a Python hardware modeling expert. Write clean Python code. If doing mathematical array operations, assume NumPy is imported and explicitly remember that * is for element-wise multiplication and @ is for matrix multiplication."
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
            messages=[
                {"role": "system", "content": "You are an HLS compiler engineer. Translate the provided Python reference model into synthesizable C++."},
                {"role": "user", "content": f"Python Code:\n{py_model.python_code}"}
            ],
            response_format=CppHlsTarget,
        )
        return CppHlsTarget.model_validate_json(response.choices[0].message.content)

# ---------------------------------------------------------------------------
# 3. Execution Block
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # A simple hardware spec to test the pipeline
    sample_spec = "Design a 4-tap moving average filter. It takes an 8-bit unsigned integer input 'data_in' and outputs an 8-bit unsigned integer 'data_out'. It updates every clock cycle."
    
    # You can easily swap this to "gemini/gemini-2.0-flash" or "anthropic/claude-3-sonnet"
    agent = CirbuildProgressiveCoder(model_name="gemini/gemini-2.5-flash") 
    
    try:
        plan = agent.understand_and_plan(sample_spec)
        py_model = agent.generate_python_gold_model(plan)
        cpp_target = agent.generate_hls_cpp(py_model)

        safe_module_name = plan.module_name.lower().replace(" ", "_").replace("-", "_")
        output_filename = f"{safe_module_name}_hls.cpp"
        
        # Write the C++ code to the working directory
        with open(output_filename, "w") as file:
            file.write(cpp_target.cpp_code)
        print(f"\n✅ Success! --- FINAL C++ HLS CODE SAVED TO: {output_filename} ---")
        print("\n--- FINAL C++ HLS CODE ---")
        print(cpp_target.cpp_code)
        
    except Exception as e:
        print(f"Pipeline failed: {e}")