from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class DataSettings:
    dw_host: str = getenv("PETROCAST_DW_HOST", "localhost")
    dw_port: int = int(getenv("PETROCAST_DW_PORT", "5432"))
    dw_user: str = getenv("PETROCAST_DW_USER", "petrocast")
    dw_password: str = getenv("PETROCAST_DW_PASSWORD", "petrocast")
    dw_database: str = getenv("PETROCAST_DW_DATABASE", "petrocast")

    @property
    def psycopg_dsn(self) -> str:
        return (
            f"host={self.dw_host} "
            f"port={self.dw_port} "
            f"dbname={self.dw_database} "
            f"user={self.dw_user} "
            f"password={self.dw_password}"
        )

    @property
    def dlt_destination_url(self) -> str:
        return (
            f"postgresql://{self.dw_user}:{self.dw_password}"
            f"@{self.dw_host}:{self.dw_port}/{self.dw_database}"
        )


settings = DataSettings()
