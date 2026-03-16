"""JSON specification schema for the Cirbuild agent → spec2rtl bridge.

Validates structured hardware specifications before they are passed
to the spec2rtl pipeline backend.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class JsonHardwareSpec(BaseModel):
    """Validated JSON schema for hardware specification input.

    This model enforces structure on the JSON that the Cirbuild agent
    produces before it is converted to text for the spec2rtl pipeline.
    """

    module_name: str = Field(
        description="Top-level hardware module name (e.g., 'ALU', 'FIFO').",
    )
    description: str = Field(
        description="Natural-language description of the module's purpose and behavior.",
    )
    inputs: Dict[str, str] = Field(
        description="Input signal names mapped to their type/width descriptions.",
    )
    outputs: Dict[str, str] = Field(
        description="Output signal names mapped to their type/width descriptions.",
    )
    behavior: str = Field(
        description="Detailed behavioral specification of the module.",
    )
    constraints: List[str] = Field(
        default_factory=list,
        description="Design constraints (timing, area, synthesis).",
    )
    classification: str = Field(
        default="COMBINATIONAL",
        description="Hardware classification: COMBINATIONAL, SEQUENTIAL_PIPELINE, or STATE_MACHINE.",
        pattern="^(COMBINATIONAL|SEQUENTIAL_PIPELINE|STATE_MACHINE)$",
    )
