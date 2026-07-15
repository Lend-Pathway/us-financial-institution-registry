"""Pydantic models for financial_institutions.json.

These model the dataset file exactly. Storage concerns (primary keys,
timestamps) belong to whatever table you load this into.

Run directly to validate the dataset:
    python3 models.py
"""

import enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InstitutionType(str, enum.Enum):
    bank = "bank"
    credit_union = "credit_union"
    fintech = "fintech"  # neobanks (Chime, Novo, Mercury). not chartered
    other = "other"


class Headquarters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: Optional[str] = None
    state: Optional[str] = Field(None, pattern=r"^[A-Z]{2}$")


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_name: Optional[str] = None       # raw registry name, unmodified
    website: Optional[str] = None
    favicon: Optional[str] = None          # verified icon URL from the site, best-effort
    headquarters: Optional[Headquarters] = None
    assets_usd: Optional[int] = Field(None, ge=0)
    deposits_usd: Optional[int] = Field(None, ge=0)   # banks only
    trade_names: Optional[list[str]] = None            # credit unions: registered DBAs
    partner_banks: Optional[list[str]] = None          # fintechs: banks holding deposits


class FinancialInstitution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")  # unique across the dataset
    display_name: str = Field(min_length=1)             # what a statement prints
    institution_type: InstitutionType

    fdic_cert: Optional[int] = Field(None, gt=0)      # banks
    ncua_charter: Optional[int] = Field(None, gt=0)   # credit unions
    rssd_id: Optional[int] = Field(None, gt=0)        # Federal Reserve, spans both

    meta: Meta = Field(default_factory=Meta)

    @model_validator(mode="after")
    def check_ids_match_type(self) -> "FinancialInstitution":
        t = self.institution_type
        if t is InstitutionType.bank:
            assert self.fdic_cert and not self.ncua_charter, "bank needs fdic_cert only"
        elif t is InstitutionType.credit_union:
            assert self.ncua_charter and not self.fdic_cert, "credit union needs ncua_charter only"
        elif t is InstitutionType.fintech:
            assert not (self.fdic_cert or self.ncua_charter or self.rssd_id), \
                "fintechs are not chartered and carry no regulator IDs"
        return self


if __name__ == "__main__":
    import json

    records = json.load(open("financial_institutions.json"))
    institutions = [FinancialInstitution(**r) for r in records]
    slugs = {i.slug for i in institutions}
    assert len(slugs) == len(institutions), "duplicate slug"
    print(f"{len(institutions)} records valid, all slugs unique")
