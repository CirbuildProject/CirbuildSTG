# CirbuildSTG

* **What is CirbuildSTG?** 
CirbuildSTG is an Agentic AI EDA tool, focusing on the Pre-silicon phase of the Integrated Circuit Design Workflow. 
The name of the tool is concatenated from "Circuit builder Spec-To-GDSII"
Leveraging the capabilities of LLMs, this tool covers the entire Frontend and Backend workflows, by integrating custom Spec2RTL generation architecture, and RTL-to-GDSII workflow tool, Librelane. Ideally achieveing an end-to-end , Spec-to-GDSII EDA tool.

* **Objectives of CirbuildSTG**
This idea is targeted to:
1) Explore possible solutions to AI driven chip design and integration of LLMs in the RTL workflow. 
2) Solve resource accessibility and guidance problems for students to learn the actual industry-standard IC design workflows.
3) Explore top-down pedagogical frameworks with LLM assistance to learn-while-building their own IC, and be able to see the layouts themselves. 

## Installation

CirbuildSTG relies on several modular subsystems, including Spec2RTL, which are managed as Python dependencies. 

**1. Clone the repository:**
```bash
git clone https://github.com/CirbuildProject/CirbuildSTG.git
cd CirbuildSTG
```

**2. Set up a virtual environment (Recommended):**
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

**3. Install dependencies:**
This command will automatically fetch and install all required packages, including the latest version of the `Cirbuild-Spec2RTL` subsystem directly from its repository.
```bash
pip install -r requirements.txt
```

## Updating Subsystems
If a new update is pushed to the Spec2RTL repository, you can force your local environment to pull the latest changes by running:
```bash
pip install --upgrade --force-reinstall git+https://github.com/CirbuildProject/Cirbuild-Spec2RTL.git@main
```

