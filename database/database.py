import sqlite3

from config import DATABASE_DIR, DATABASE_PATH


def get_connection():

    DATABASE_DIR.mkdir(exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def init_database():

    connection = get_connection()

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS tournament_series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );


        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER,
            name TEXT NOT NULL,
            format TEXT NOT NULL,
            tournament_date TEXT NOT NULL,
            rounds INTEGER NOT NULL DEFAULT 3,
            status TEXT NOT NULL DEFAULT 'planned',
            historical INTEGER NOT NULL DEFAULT 0,
            current_round INTEGER DEFAULT 0,
            counts_for_top8 INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (series_id)
                REFERENCES tournament_series(id)
                ON DELETE SET NULL
        );


        CREATE TABLE IF NOT EXISTS tournament_players (
            tournament_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,

            seat_number INTEGER,

            PRIMARY KEY (tournament_id, player_id),

            FOREIGN KEY (tournament_id)
                REFERENCES tournaments(id)
                ON DELETE CASCADE,

            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE
        );


        CREATE TABLE IF NOT EXISTS series_players (
            series_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,

            PRIMARY KEY (series_id, player_id),

            FOREIGN KEY (series_id)
                REFERENCES tournament_series(id)
                ON DELETE CASCADE,

            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE
        );


        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            started_at TIMESTAMP,
            finished_at TIMESTAMP,

            UNIQUE (tournament_id, round_number),

            FOREIGN KEY (tournament_id)
                REFERENCES tournaments(id)
                ON DELETE CASCADE
        );


        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,

            player1_id INTEGER,
            player2_id INTEGER,

            player1_games INTEGER DEFAULT 0,
            player2_games INTEGER DEFAULT 0,

            result TEXT,

            table_number INTEGER,

            FOREIGN KEY (round_id)
                REFERENCES rounds(id)
                ON DELETE CASCADE,

            FOREIGN KEY (player1_id)
                REFERENCES players(id),

            FOREIGN KEY (player2_id)
                REFERENCES players(id)
        );
        """
    )


    # ==========================================
    # EINDEUTIGE SPIELERNAMEN
    # ==========================================

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_players_name_unique
        ON players(name COLLATE NOCASE)
        """
    )


    connection.commit()

    connection.close()
