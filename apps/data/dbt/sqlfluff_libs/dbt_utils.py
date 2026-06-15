"""sqlfluff jinja stubs for dbt_utils macros.

sqlfluff lints with the jinja templater (no live dbt / no dbt_packages), so
dbt_utils macros are undefined at lint time. These stubs return valid scalar
SQL so models that call dbt_utils parse and lint; dbt runtime uses the real
macros from the installed package.
"""


def generate_surrogate_key(field_list):
    return "md5('sqlfluff_stub')"
