{% macro non_negative(column_name) %}
    {#-
      Bronze -> Silver cast for production measures: blank -> NULL (the source
      uses empty strings for "not reported") and negative -> NULL.

      Negative months are rectificaciones de DDJJ, not measurements (3 rows in
      410k as of 2026-05). Nulling them keeps the `accepted_range` checks on
      silver_production blocking (F2-18) without clamping to 0, which would
      assert the well produced nothing when the truth is that we don't know.

      Zero is preserved: an idle well reporting 0 is a real measurement, and
      the feature store counts those months (`zero_months_12m`).
    -#}
    case
        when cast(nullif(trim({{ column_name }}), '') as numeric) >= 0
            then cast(nullif(trim({{ column_name }}), '') as numeric)
    end
{% endmacro %}
