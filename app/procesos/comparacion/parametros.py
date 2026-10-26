"""Parámetros de las tres fases. Se guardan en nucleo.trabajo.parametros al encolar, así un reintento
usa los mismos valores aunque después cambie la configuración."""

from dataclasses import dataclass
from decimal import Decimal

from app import config


@dataclass(frozen=True)
class ParametrosFases:
    tolerancia: Decimal  # fases 1 y 2: diferencia aceptada en montos
    tasa_igv: Decimal  # fase 3: IGV + IPM (0.18)
    tolerancia_igv: Decimal  # fase 3: el IGV se redondea línea por línea y puede diferir unos céntimos

    @classmethod
    def desde_config(cls) -> "ParametrosFases":
        cfg = config.cargar()
        return cls(cfg.tolerancia, cfg.tasa_igv, cfg.tolerancia_igv)

    @classmethod
    def desde_trabajo(cls, parametros: dict) -> "ParametrosFases":
        """Los trabajos encolados antes de las fases 2 y 3 solo tienen la tolerancia."""
        por_defecto = cls.desde_config()
        return cls(
            Decimal(str(parametros.get("tolerancia", por_defecto.tolerancia))),
            Decimal(str(parametros.get("tasa_igv", por_defecto.tasa_igv))),
            Decimal(str(parametros.get("tolerancia_igv", por_defecto.tolerancia_igv))),
        )

    def a_dict(self) -> dict[str, str]:
        return {"tolerancia": str(self.tolerancia), "tasa_igv": str(self.tasa_igv),
                "tolerancia_igv": str(self.tolerancia_igv)}
