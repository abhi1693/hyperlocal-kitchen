"""Community choices shared by API contracts, persistence and generated UI labels."""

from enum import StrEnum


class CommunityType(StrEnum):
    residential_society = "residential_society"
    cantonment = "cantonment"
    housing_colony = "housing_colony"
    university = "university"
    corporate_campus = "corporate_campus"
    gated_community = "gated_community"
    other = "other"

    @property
    def slug(self) -> str:
        return self.value

    @property
    def label(self) -> str:
        return {
            self.residential_society: "Residential society",
            self.cantonment: "Cantonment",
            self.housing_colony: "Housing colony",
            self.university: "University",
            self.corporate_campus: "Corporate campus",
            self.gated_community: "Gated community",
            self.other: "Other",
        }[self]

    @classmethod
    def choices(cls) -> list[dict[str, str]]:
        return [{"slug": item.slug, "label": item.label} for item in cls]

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(core_schema)
        schema = handler.resolve_ref_schema(schema)
        schema["x-choices"] = cls.choices()
        return schema
