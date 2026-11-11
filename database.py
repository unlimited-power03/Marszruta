
import sqlite3
import re
from pathlib import Path
from datetime import datetime


# Baza danych zapisywana obok plikow .py
DB_PATH = Path(__file__).resolve().parent / "produkcja.db"


def polacz():
    """Tworzy polaczenie z baza danych."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def pobierz_najwyzszy_numer_z_bazy(conn):
    """Zwraca najwyzszy numer zamowienia zapisanego w bazie."""

    rekordy = conn.execute("""
        SELECT id
        FROM zamowienia
    """).fetchall()

    najwyzszy = 0

    for rekord in rekordy:
        dopasowanie = re.fullmatch(r"ZAM-(\d+)", rekord["id"])

        if dopasowanie:
            numer = int(dopasowanie.group(1))
            najwyzszy = max(najwyzszy, numer)

    return najwyzszy


def inicjalizuj_baze():
    """Tworzy tabele i wykonuje migracje istniejacej bazy."""

    with polacz() as conn:

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS zamowienia (
                id TEXT PRIMARY KEY,
                plik_xml TEXT NOT NULL,
                typ TEXT NOT NULL,
                model TEXT NOT NULL,
                rozmiar TEXT NOT NULL,
                ilosc INTEGER NOT NULL,

                status TEXT NOT NULL DEFAULT 'OCZEKUJE',

                status_przekazania TEXT NOT NULL DEFAULT 'OCZEKUJE',
                data_przekazania TEXT,

                status_archiwizacji TEXT NOT NULL DEFAULT 'NIE_DOTYCZY',

                data_dodania TEXT NOT NULL,
                data_startu TEXT,
                data_zakonczenia TEXT,

                czas_realizacji_min REAL DEFAULT 0,
                liczba_poprawek INTEGER DEFAULT 0,
                komunikat TEXT
            );

            CREATE TABLE IF NOT EXISTS rowery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                zamowienie_id TEXT NOT NULL,
                numer_sztuki INTEGER NOT NULL,

                status TEXT NOT NULL DEFAULT 'OCZEKUJE',
                aktualne_stanowisko TEXT,

                czas_startu_min REAL,
                czas_zakonczenia_min REAL,

                FOREIGN KEY (zamowienie_id)
                    REFERENCES zamowienia(id)
                    ON DELETE CASCADE,

                UNIQUE(zamowienie_id, numer_sztuki)
            );

            CREATE TABLE IF NOT EXISTS operacje (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                rower_id INTEGER NOT NULL,
                stanowisko TEXT NOT NULL,

                czas_startu_min REAL NOT NULL,
                czas_zakonczenia_min REAL NOT NULL,
                czas_trwania_min REAL NOT NULL,

                status TEXT NOT NULL,
                opis TEXT,

                FOREIGN KEY (rower_id)
                    REFERENCES rowery(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS licznik_zamowien (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                ostatni_numer INTEGER NOT NULL
            );
        """)

        # Migracje tabeli rowery
        kolumny_rowery = {
            kolumna["name"]
            for kolumna in conn.execute(
                "PRAGMA table_info(rowery)"
            ).fetchall()
        }

        if "liczba_poprawek" not in kolumny_rowery:
            conn.execute("""
                ALTER TABLE rowery
                ADD COLUMN liczba_poprawek INTEGER NOT NULL DEFAULT 0
            """)

        if "ostatnia_usterka" not in kolumny_rowery:
            conn.execute("""
                ALTER TABLE rowery
                ADD COLUMN ostatnia_usterka TEXT
            """)

        # Migracje tabeli zamowienia
        kolumny_zamowienia = {
            kolumna["name"]
            for kolumna in conn.execute(
                "PRAGMA table_info(zamowienia)"
            ).fetchall()
        }

        if "status_przekazania" not in kolumny_zamowienia:
            conn.execute("""
                ALTER TABLE zamowienia
                ADD COLUMN status_przekazania TEXT NOT NULL
                DEFAULT 'PRZEKAZANE'
            """)

        if "data_przekazania" not in kolumny_zamowienia:
            conn.execute("""
                ALTER TABLE zamowienia
                ADD COLUMN data_przekazania TEXT
            """)

        if "status_archiwizacji" not in kolumny_zamowienia:
            conn.execute("""
                ALTER TABLE zamowienia
                ADD COLUMN status_archiwizacji TEXT NOT NULL
                DEFAULT 'NIE_DOTYCZY'
            """)

        # Wykrywanie starszych zakonczonych zamowien,
        # ktorych pliki XML nadal znajduja sie na dysku.
        zakonczone = conn.execute("""
            SELECT id, plik_xml
            FROM zamowienia
            WHERE status IN (
                'ZREALIZOWANE',
                'ODRZUCONE',
                'CZESCIOWO_ZREALIZOWANE'
            )
            AND status_archiwizacji = 'NIE_DOTYCZY'
        """).fetchall()

        for zamowienie in zakonczone:
            if Path(zamowienie["plik_xml"]).is_file():
                conn.execute("""
                    UPDATE zamowienia
                    SET status_archiwizacji = 'OCZEKUJE'
                    WHERE id = ?
                """, (zamowienie["id"],))

        # Inicjalizacja licznika zamowien
        najwyzszy_numer = pobierz_najwyzszy_numer_z_bazy(conn)

        licznik = conn.execute("""
            SELECT ostatni_numer
            FROM licznik_zamowien
            WHERE id = 1
        """).fetchone()

        if licznik is None:
            conn.execute("""
                INSERT INTO licznik_zamowien (id, ostatni_numer)
                VALUES (1, ?)
            """, (najwyzszy_numer,))

        elif licznik["ostatni_numer"] < najwyzszy_numer:
            conn.execute("""
                UPDATE licznik_zamowien
                SET ostatni_numer = ?
                WHERE id = 1
            """, (najwyzszy_numer,))

    print(f"Baza danych gotowa: {DB_PATH.name}")


def zarezerwuj_numer_zamowienia():
    """Rezerwuje kolejny numer zamowienia."""

    with polacz() as conn:

        conn.execute("BEGIN IMMEDIATE")

        licznik = conn.execute("""
            SELECT ostatni_numer
            FROM licznik_zamowien
            WHERE id = 1
        """).fetchone()

        if licznik is None:
            raise RuntimeError(
                "Brak licznika zamowien. "
                "Uruchom najpierw inicjalizuj_baze()."
            )

        nowy_numer = licznik["ostatni_numer"] + 1

        conn.execute("""
            UPDATE licznik_zamowien
            SET ostatni_numer = ?
            WHERE id = 1
        """, (nowy_numer,))

    return f"ZAM-{nowy_numer:04d}"


def zarejestruj_zamowienie(
    zamowienie_id,
    plik_xml,
    typ,
    model,
    rozmiar,
    ilosc
):
    """Rejestruje zamowienie i tworzy rekord dla kazdego roweru."""

    with polacz() as conn:

        cursor = conn.execute("""
            INSERT OR IGNORE INTO zamowienia (
                id,
                plik_xml,
                typ,
                model,
                rozmiar,
                ilosc,
                status,
                status_przekazania,
                status_archiwizacji,
                data_dodania
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                'OCZEKUJE',
                'OCZEKUJE',
                'NIE_DOTYCZY',
                ?
            )
        """, (
            zamowienie_id,
            str(plik_xml),
            typ,
            model,
            rozmiar,
            ilosc,
            datetime.now().isoformat(timespec="seconds")
        ))

        if cursor.rowcount == 0:
            return False

        for numer in range(1, ilosc + 1):
            conn.execute("""
                INSERT INTO rowery (
                    zamowienie_id,
                    numer_sztuki
                )
                VALUES (?, ?)
            """, (zamowienie_id, numer))

    return True


def pobierz_zamowienia_do_przekazania():
    """Pobiera zamowienia oczekujace na przekazanie do produkcji."""

    with polacz() as conn:
        rekordy = conn.execute("""
            SELECT
                id,
                plik_xml,
                typ,
                model,
                rozmiar,
                ilosc
            FROM zamowienia
            WHERE status_przekazania = 'OCZEKUJE'
            ORDER BY data_dodania, id
        """).fetchall()

    return [dict(rekord) for rekord in rekordy]


def oznacz_zamowienie_przekazane(zamowienie_id, nowy_plik_xml):
    """Oznacza zamowienie jako przekazane do produkcji."""

    with polacz() as conn:
        cursor = conn.execute("""
            UPDATE zamowienia
            SET status_przekazania = 'PRZEKAZANE',
                plik_xml = ?,
                data_przekazania = ?
            WHERE id = ?
              AND status_przekazania = 'OCZEKUJE'
        """, (
            str(nowy_plik_xml),
            datetime.now().isoformat(timespec="seconds"),
            zamowienie_id
        ))

        return cursor.rowcount > 0


def ustaw_status_zamowienia(
    zamowienie_id,
    status,
    komunikat=None
):
    """Aktualizuje status produkcyjny zamowienia."""

    with polacz() as conn:
        conn.execute("""
            UPDATE zamowienia
            SET status = ?,
                komunikat = ?
            WHERE id = ?
        """, (status, komunikat, zamowienie_id))


def zakoncz_zamowienie(
    zamowienie_id,
    czas_realizacji_min,
    status
):
    """
    Zapisuje koncowy wynik produkcji zamowienia.

    Archiwizacja jest oznaczana jako OCZEKUJE.
    Osobny etap przeniesie plik XML i zmieni ten status.
    """

    dozwolone_statusy = {
        "ZREALIZOWANE",
        "ODRZUCONE",
        "CZESCIOWO_ZREALIZOWANE"
    }

    if status not in dozwolone_statusy:
        raise ValueError(f"Nieprawidlowy status zamowienia: {status}")

    with polacz() as conn:
        conn.execute("""
            UPDATE zamowienia
            SET status = ?,
                data_zakonczenia = ?,
                czas_realizacji_min = ?,
                status_archiwizacji = 'OCZEKUJE'
            WHERE id = ?
        """, (
            status,
            datetime.now().isoformat(timespec="seconds"),
            czas_realizacji_min,
            zamowienie_id
        ))


def pobierz_zamowienia_do_archiwizacji():
    """
    Pobiera zakonczone zamowienia, ktorych XML
    oczekuje na przeniesienie do archiwum.
    """

    with polacz() as conn:
        rekordy = conn.execute("""
            SELECT
                id,
                plik_xml,
                typ,
                status,
                data_zakonczenia,
                czas_realizacji_min
            FROM zamowienia
            WHERE status IN (
                'ZREALIZOWANE',
                'ODRZUCONE',
                'CZESCIOWO_ZREALIZOWANE'
            )
            AND status_archiwizacji IN ('OCZEKUJE', 'BLAD')
            ORDER BY data_zakonczenia, id
        """).fetchall()

    return [dict(rekord) for rekord in rekordy]


def oznacz_zamowienie_zarchiwizowane(
    zamowienie_id,
    nowy_plik_xml
):
    """
    Zapisuje nowa sciezke XML i potwierdza archiwizacje.
    """

    with polacz() as conn:
        cursor = conn.execute("""
            UPDATE zamowienia
            SET plik_xml = ?,
                status_archiwizacji = 'ZARCHIWIZOWANO',
                komunikat = NULL
            WHERE id = ?
              AND status IN (
                  'ZREALIZOWANE',
                  'ODRZUCONE',
                  'CZESCIOWO_ZREALIZOWANE'
              )
              AND status_archiwizacji IN ('OCZEKUJE', 'BLAD')
        """, (str(nowy_plik_xml), zamowienie_id))

        return cursor.rowcount > 0


def oznacz_blad_archiwizacji(zamowienie_id, komunikat):
    """Zapisuje blad archiwizacji, ktory mozna ponowic."""

    with polacz() as conn:
        conn.execute("""
            UPDATE zamowienia
            SET status_archiwizacji = 'BLAD',
                komunikat = ?
            WHERE id = ?
              AND status IN (
                  'ZREALIZOWANE',
                  'ODRZUCONE',
                  'CZESCIOWO_ZREALIZOWANE'
              )
        """, (komunikat, zamowienie_id))


def ustaw_status_roweru(
    zamowienie_id,
    numer_sztuki,
    status,
    stanowisko=None
):
    """Aktualizuje status pojedynczego roweru."""

    with polacz() as conn:
        conn.execute("""
            UPDATE rowery
            SET status = ?,
                aktualne_stanowisko = ?
            WHERE zamowienie_id = ?
              AND numer_sztuki = ?
        """, (
            status,
            stanowisko,
            zamowienie_id,
            numer_sztuki
        ))


def dodaj_operacje(
    zamowienie_id,
    numer_sztuki,
    stanowisko,
    czas_startu,
    czas_zakonczenia,
    status="ZAKONCZONA",
    opis=None
):
    """Zapisuje przebieg operacji produkcyjnej."""

    czas_trwania = czas_zakonczenia - czas_startu

    with polacz() as conn:

        rower = conn.execute("""
            SELECT id
            FROM rowery
            WHERE zamowienie_id = ?
              AND numer_sztuki = ?
        """, (zamowienie_id, numer_sztuki)).fetchone()

        if rower is None:
            raise ValueError(
                f"Nie znaleziono roweru: "
                f"{zamowienie_id}, sztuka {numer_sztuki}"
            )

        conn.execute("""
            INSERT INTO operacje (
                rower_id,
                stanowisko,
                czas_startu_min,
                czas_zakonczenia_min,
                czas_trwania_min,
                status,
                opis
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            rower["id"],
            stanowisko,
            czas_startu,
            czas_zakonczenia,
            czas_trwania,
            status,
            opis
        ))


def pobierz_statystyki():
    """Zwraca podstawowe statystyki bazy."""

    with polacz() as conn:

        zamowienia = conn.execute("""
            SELECT status, COUNT(*) AS liczba
            FROM zamowienia
            GROUP BY status
        """).fetchall()

        rowery = conn.execute("""
            SELECT status, COUNT(*) AS liczba
            FROM rowery
            GROUP BY status
        """).fetchall()

        przekazanie = conn.execute("""
            SELECT status_przekazania, COUNT(*) AS liczba
            FROM zamowienia
            GROUP BY status_przekazania
        """).fetchall()

        archiwizacja = conn.execute("""
            SELECT status_archiwizacji, COUNT(*) AS liczba
            FROM zamowienia
            GROUP BY status_archiwizacji
        """).fetchall()

        operacje = conn.execute("""
            SELECT COUNT(*) AS liczba
            FROM operacje
        """).fetchone()

        licznik = conn.execute("""
            SELECT ostatni_numer
            FROM licznik_zamowien
            WHERE id = 1
        """).fetchone()

    return {
        "zamowienia": {
            row["status"]: row["liczba"]
            for row in zamowienia
        },
        "rowery": {
            row["status"]: row["liczba"]
            for row in rowery
        },
        "przekazanie": {
            row["status_przekazania"]: row["liczba"]
            for row in przekazanie
        },
        "archiwizacja": {
            row["status_archiwizacji"]: row["liczba"]
            for row in archiwizacja
        },
        "ostatni_numer": (
            licznik["ostatni_numer"] if licznik else 0
        ),
        "liczba_operacji": operacje["liczba"]
    }


if __name__ == "__main__":
    inicjalizuj_baze()
    print("Statystyki:", pobierz_statystyki())
