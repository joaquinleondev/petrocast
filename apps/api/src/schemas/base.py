from pydantic import BaseModel, ConfigDict


def _snake_case(field_name: str) -> str:
    return field_name


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_snake_case,
        populate_by_name=True,
    )
