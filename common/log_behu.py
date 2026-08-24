"""Detailni log behu: nejdriv do souboru, potom do databaze.

Proc v tomhle poradi:
    Do SOUBORU se zapisuje PRUBEZNE s flushem po kazdem radku - jen tak jde
    beh sledovat zaziva a hlavne log PREZIJE PAD kroku. Do DB az davkove
    po skonceni; kdyby se zapisovalo prubezne, pad uprostred transakce by
    log zahodil.

Format radku (viz todo.md):
    cas | krok | lecivo | sekce | akce | stav | vysledek | trvani

Vysledek je vzdy ve tvaru hotovo/celkem, at je videt uspesnost, ne jen
"hotovo" - 4/6 a 6/6 jsou dve velmi ruzne veci.

Stavy se pouzivaji STEJNE jako v stavy.md, nezavadi se druhy slovnik.

Pouziti:
    log = LogBehu("krok3")
    log.zaznam("0254048_PARALEN", "indikace", "extrakce",
               stav="ok", hotovo=7, celkem=7, trvani_s=11.7)
    log.zaviri()          # dopise souhrn a ulozi do DB
"""

import io
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ADRESAR = Path("logs")

DDL = """
CREATE TABLE IF NOT EXISTS beh_log (
    id          BIGSERIAL PRIMARY KEY,
    beh_id      TEXT NOT NULL,      -- jeden spusteny krok = jedno beh_id
    cas         TIMESTAMPTZ NOT NULL,
    krok        TEXT NOT NULL,      -- krok1..krok5, krok4a, krok4b, embedding
    lecivo      TEXT,               -- adresar leciva, NULL u celkovych zaznamu
    sekce       TEXT,
    akce        TEXT NOT NULL,      -- extrakce | kontrola | embedding | ...
    stav        TEXT NOT NULL,      -- slovnik ze stavy.md
    hotovo      INTEGER,
    celkem      INTEGER,
    trvani_s    NUMERIC,
    poznamka    TEXT
);
CREATE INDEX IF NOT EXISTS beh_log_beh_idx    ON beh_log (beh_id);
CREATE INDEX IF NOT EXISTS beh_log_lecivo_idx ON beh_log (lecivo);
CREATE INDEX IF NOT EXISTS beh_log_stav_idx   ON beh_log (stav);
"""


class LogBehu:
    """Log jednoho spusteneho kroku."""

    def __init__(self, krok: str, *, adresar: Path | None = None,
                 do_db: bool = True, tichy: bool = False):
        self.krok = krok
        self.do_db = do_db
        self.tichy = tichy
        self.zacatek = datetime.now()
        self.beh_id = f"{self.zacatek:%Y%m%d_%H%M%S}_{krok}"
        self.zaznamy: list[dict] = []

        adr = adresar or ADRESAR
        adr.mkdir(parents=True, exist_ok=True)
        self.soubor = adr / f"{self.zacatek:%Y-%m-%d}_{krok}.log"

        # line_buffering=True -> flush po kazdem radku. Bez toho by se pri
        # padu kroku ztratil cely dosavadni prubeh.
        self._f = io.open(self.soubor, "a", encoding="utf-8", buffering=1)
        self._pis(f"# === beh {self.beh_id} zahajen {self.zacatek:%Y-%m-%d %H:%M:%S} ===")

    def _pis(self, radek: str) -> None:
        # buffering=1 na souboru zajistuje flush po kazdem radku
        self._f.write(radek + "\n")
        if not self.tichy:
            print(radek, flush=True)

    def zaznam(self, lecivo: str | None, sekce: str | None, akce: str, *,
               stav: str, hotovo: int | None = None, celkem: int | None = None,
               trvani_s: float | None = None, poznamka: str = "") -> None:
        cas = datetime.now()

        # Vysledek VZDY jako hotovo/celkem - z "hotovo" nejde poznat,
        # jestli se povedlo 6 ze 6 nebo 4 ze 6.
        if hotovo is not None and celkem is not None:
            vysledek = f"{hotovo}/{celkem}"
        elif hotovo is not None:
            vysledek = str(hotovo)
        else:
            vysledek = "-"

        trvani = f"{trvani_s:6.1f}s" if trvani_s is not None else "      -"

        radek = (f"{cas:%H:%M:%S} | {self.krok:8} | {(lecivo or '-')[:30]:30} | "
                 f"{(sekce or '-'):18} | {akce:10} | {stav:20} | "
                 f"{vysledek:>10} | {trvani}")
        if poznamka:
            radek += f"  {poznamka}"
        self._pis(radek)
        self.zaznamy.append({
            "beh_id": self.beh_id, "cas": cas, "krok": self.krok,
            "lecivo": lecivo, "sekce": sekce, "akce": akce, "stav": stav,
            "hotovo": hotovo, "celkem": celkem, "trvani_s": trvani_s,
            "poznamka": poznamka or None,
        })

    def souhrn(self) -> dict[str, int]:
        from collections import Counter
        return dict(Counter(z["stav"] for z in self.zaznamy))

    def zaviri(self) -> None:
        trvalo = (datetime.now() - self.zacatek).total_seconds()
        s = self.souhrn()
        self._pis(f"# === beh {self.beh_id} hotov za {trvalo/60:.1f} min, "
                  f"zaznamu {len(self.zaznamy)}, stavy: {s} ===")
        self._f.close()

        if self.do_db:
            ulozeno = self._do_db()
            print(f"Log: {self.soubor}"
                  + (f", do DB zapsano {ulozeno} zaznamu" if ulozeno else
                     ", do DB se zapsat NEPODARILO (soubor zustava)"))
        else:
            print(f"Log: {self.soubor}")

    def _do_db(self) -> int:
        """Davkovy zapis do DB. Kdyz selze, log v souboru uz existuje -
        proto se chyba jen zaloguje a beh se kvuli ni neshodi."""
        if not self.zaznamy:
            return 0
        try:
            import psycopg

            from common.config import PG_DSN

            with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
                cur.execute(DDL)
                cur.executemany("""
                    INSERT INTO beh_log (beh_id, cas, krok, lecivo, sekce, akce,
                                         stav, hotovo, celkem, trvani_s, poznamka)
                    VALUES (%(beh_id)s,%(cas)s,%(krok)s,%(lecivo)s,%(sekce)s,
                            %(akce)s,%(stav)s,%(hotovo)s,%(celkem)s,
                            %(trvani_s)s,%(poznamka)s)
                """, self.zaznamy)
                conn.commit()
            return len(self.zaznamy)
        except Exception as e:
            logger.warning("zapis logu do DB selhal: %s: %s", type(e).__name__, e)
            return 0
