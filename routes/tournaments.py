from multiprocessing import connection
import random
from datetime import datetime

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for
)

from database.database import get_connection


tournaments = Blueprint(
    "tournaments",
    __name__,
    url_prefix="/tournaments"
)


def is_top8_format(tournament_format):
    return (
        tournament_format == "Top 8"
        or tournament_format.startswith("Top 8 ")
    )


def top8_game_format(tournament_format):
    if tournament_format == "Top 8":
        return "Draft"

    return tournament_format.removeprefix("Top 8 ")


@tournaments.route("/")
def list_tournaments():

    connection = get_connection()

    tournament_list = connection.execute(
        """
        SELECT
            t.*,
            s.name AS series_name
        FROM tournaments t

        LEFT JOIN tournament_series s
            ON s.id = t.series_id

        ORDER BY
            t.tournament_date DESC,
            t.id DESC
        """
    ).fetchall()

    connection.close()

    return render_template(
        "tournaments.html",
        tournaments=tournament_list
    )


@tournaments.route("/new", methods=["GET", "POST"])
def new_tournament():

    selected_series_id = request.args.get(
        "series_id",
        ""
    )

    connection = get_connection()

    series_list = connection.execute(
        """
        SELECT *
        FROM tournament_series

        ORDER BY
            COALESCE(start_date, '') DESC,
            name
        """
    ).fetchall()


    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        tournament_format = request.form.get(
            "format",
            ""
        ).strip()

        tournament_date = request.form.get(
            "date",
            ""
        ).strip()

        rounds = request.form.get(
            "rounds",
            "3"
        ).strip()

        series_id = request.form.get(
            "series_id",
            ""
        ).strip()

        historical = (
            1
            if request.form.get("historical")
            else 0
        )

        counts_for_top8 = (
            1
            if request.form.get("counts_for_top8")
            else 0
        )


        allowed_formats = {
            "Draft",
            "Sealed",
            "Constructed"
        }


        if (
            not name
            or not tournament_format
            or not tournament_date
        ):

            connection.close()

            return render_template(
                "tournament_form.html",
                error="Bitte alle Pflichtfelder ausfüllen.",
                series_list=series_list,
                selected_series_id=series_id
            )


        if tournament_format not in allowed_formats:

            connection.close()

            return render_template(
                "tournament_form.html",
                error="Ungültiges Turnierformat.",
                series_list=series_list,
                selected_series_id=series_id
            )


        try:

            rounds_value = int(rounds)

        except ValueError:

            connection.close()

            return render_template(
                "tournament_form.html",
                error="Die Anzahl der Runden muss eine Zahl sein.",
                series_list=series_list,
                selected_series_id=series_id
            )


        if rounds_value < 1:

            connection.close()

            return render_template(
                "tournament_form.html",
                error="Es muss mindestens eine Runde geben.",
                series_list=series_list,
                selected_series_id=series_id
            )


        series_value = (
            int(series_id)
            if series_id
            else None
        )

        if series_value is not None:
            existing_top8 = connection.execute(
                """
                SELECT id
                FROM tournaments
                WHERE series_id = ?
                  AND format LIKE 'Top 8%'
                LIMIT 1
                """,
                (series_value,)
            ).fetchone()

            if existing_top8 is not None:
                connection.close()
                return render_template(
                    "tournament_form.html",
                    error=(
                        "Für diese Serie kann kein weiteres Turnier "
                        "angelegt werden, sobald eine Top 8 existiert."
                    ),
                    series_list=series_list,
                    selected_series_id=series_id
                )

        cursor = connection.execute(
            """
            INSERT INTO tournaments
            (
                series_id,
                name,
                format,
                tournament_date,
                rounds,
                historical,
                counts_for_top8
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                series_value,
                name,
                tournament_format,
                tournament_date,
                rounds_value,
                historical,
                counts_for_top8
            )
        )


        tournament_id = cursor.lastrowid


        # Teilnehmer der Serie automatisch übernehmen
        if series_value:

            connection.execute(
                """
                INSERT OR IGNORE INTO tournament_players
                (
                    tournament_id,
                    player_id
                )

                SELECT
                    ?,
                    player_id

                FROM series_players

                WHERE series_id = ?
                """,
                (
                    tournament_id,
                    series_value
                )
            )


        connection.commit()
        connection.close()


        if series_value:

            return redirect(
                url_for(
                    "series.show_series",
                    series_id=series_value
                )
            )


        return redirect(
            url_for(
                "tournaments.list_tournaments"
            )
        )


    connection.close()


    return render_template(
        "tournament_form.html",
        series_list=series_list,
        selected_series_id=selected_series_id
    )


@tournaments.route("/<int:tournament_id>")
def tournament(tournament_id):

    changed = (
        request.args.get("changed") == "1"
    )

    edit_results = (
        request.args.get("edit") == "1"
    )

    connection = get_connection()

    tournament_data = connection.execute(
        """
        SELECT
            t.*,
            s.name AS series_name
        FROM tournaments t

        LEFT JOIN tournament_series s
            ON s.id = t.series_id

        WHERE t.id = ?
        """,
        (tournament_id,)
    ).fetchone()


    if tournament_data is None:

        connection.close()

        return "Turnier nicht gefunden", 404


    tournament_players = connection.execute(
        """
        SELECT
            p.id,
            p.name,
            tp.seat_number
        FROM players p
        JOIN tournament_players tp
            ON tp.player_id = p.id
        WHERE tp.tournament_id = ?
        ORDER BY
            CASE
                WHEN tp.seat_number IS NULL THEN 999999
                ELSE tp.seat_number
            END,
            p.name
        """,
        (tournament_id,)
    ).fetchall()


    available_players = connection.execute(
        """
        SELECT
            p.id,
            p.name
        FROM players p

        WHERE p.active = 1

          AND p.id NOT IN (
              SELECT player_id
              FROM tournament_players
              WHERE tournament_id = ?
          )

        ORDER BY p.name
        """,
        (tournament_id,)
    ).fetchall()


    series_players = []

    if tournament_data["series_id"]:

        series_players = connection.execute(
            """
            SELECT
                p.id,
                p.name
            FROM players p

            JOIN series_players sp
                ON sp.player_id = p.id

            WHERE sp.series_id = ?

              AND p.id NOT IN (
                  SELECT player_id
                  FROM tournament_players
                  WHERE tournament_id = ?
              )

            ORDER BY p.name
            """,
            (
                tournament_data["series_id"],
                tournament_id
            )
        ).fetchall()


    # Aktuelle Runde
    current_round = None

    if tournament_data["current_round"] > 0:

        current_round = connection.execute(
            """
            SELECT *
            FROM rounds

            WHERE tournament_id = ?
              AND round_number = ?
            """,
            (
                tournament_id,
                tournament_data["current_round"]
            )
        ).fetchone()

    # Paarungen der aktuellen Runde
    matches = []

    if current_round:

        matches = connection.execute(
            """
            SELECT
                m.id,
                m.player1_id,
                m.player2_id,
                m.player1_games,
                m.player2_games,
                m.result,
                m.table_number,

                p1.name AS player1_name,
                p2.name AS player2_name

            FROM matches m

            LEFT JOIN players p1
                ON p1.id = m.player1_id

            LEFT JOIN players p2
                ON p2.id = m.player2_id

            WHERE m.round_id = ?

            ORDER BY m.table_number
            """,
            (current_round["id"],)
        ).fetchall()

    # Vergangene Runden
    past_rounds = connection.execute(
            """
            SELECT
                r.id,
                r.round_number,
                r.status,
                r.started_at,
                r.finished_at
            FROM rounds r
            WHERE r.tournament_id = ?
            AND r.round_number < ?
            ORDER BY r.round_number DESC
            """,
            (
                tournament_id,
                current_round["round_number"]
                if current_round
                else 0
            )
        ).fetchall()

    past_round_matches = {}

    for past_round in past_rounds:

        round_matches = connection.execute(
            """
            SELECT
                m.id,
                m.player1_id,
                m.player2_id,
                m.player1_games,
                m.player2_games,
                m.result,
                m.table_number,

                p1.name AS player1_name,
                p2.name AS player2_name

            FROM matches m

            LEFT JOIN players p1
                ON p1.id = m.player1_id

            LEFT JOIN players p2
                ON p2.id = m.player2_id

            WHERE m.round_id = ?

            ORDER BY m.table_number
            """,
            (past_round["id"],)
        ).fetchall()

        past_round_matches[
            past_round["id"]
        ] = round_matches

    connection.close()


    return render_template(
        "tournament.html",
        changed=changed,
        tournament=tournament_data,
        tournament_players=tournament_players,
        available_players=available_players,
        series_players=series_players,
        current_round=current_round,
        matches=matches,
        edit_results=edit_results,
        past_rounds=past_rounds,
        past_round_matches=past_round_matches
    )


@tournaments.route(
    "/<int:tournament_id>/add-player",
    methods=["POST"]
)
def add_player(tournament_id):

    player_id = request.form.get(
        "player_id",
        ""
    ).strip()


    if player_id:

        connection = get_connection()

        connection.execute(
            """
            INSERT OR IGNORE INTO tournament_players
            (
                tournament_id,
                player_id
            )
            VALUES (?, ?)
            """,
            (
                tournament_id,
                int(player_id)
            )
        )

        connection.commit()
        connection.close()


    return redirect(
        url_for(
            "tournaments.tournament",
            tournament_id=tournament_id
        )
    )


@tournaments.route(
    "/<int:tournament_id>/remove-player",
    methods=["POST"]
)
def remove_player(tournament_id):

    player_id = request.form.get(
        "player_id",
        ""
    ).strip()


    if player_id:

        connection = get_connection()

        connection.execute(
            """
            DELETE FROM tournament_players

            WHERE tournament_id = ?
              AND player_id = ?
            """,
            (
                tournament_id,
                int(player_id)
            )
        )

        connection.commit()
        connection.close()


    return redirect(
        url_for(
            "tournaments.tournament",
            tournament_id=tournament_id
        )
    )


@tournaments.route(
    "/<int:tournament_id>/import-series-players",
    methods=["POST"]
)
def import_series_players(tournament_id):

    connection = get_connection()

    tournament = connection.execute(
        """
        SELECT series_id
        FROM tournaments
        WHERE id = ?
        """,
        (tournament_id,)
    ).fetchone()


    if tournament is None:

        connection.close()

        return "Turnier nicht gefunden", 404


    series_id = tournament["series_id"]


    if series_id:

        connection.execute(
            """
            INSERT OR IGNORE INTO tournament_players
            (
                tournament_id,
                player_id
            )

            SELECT
                ?,
                player_id

            FROM series_players

            WHERE series_id = ?
            """,
            (
                tournament_id,
                series_id
            )
        )

        connection.commit()


    connection.close()


    return redirect(
        url_for(
            "tournaments.tournament",
            tournament_id=tournament_id
        )
    )

@tournaments.route(
    "/<int:tournament_id>/seating"
)
def seating(tournament_id):

    connection = get_connection()

    tournament = connection.execute(
        """
        SELECT
            t.*,
            s.name AS series_name
        FROM tournaments t
        LEFT JOIN tournament_series s
            ON s.id = t.series_id
        WHERE t.id = ?
        """,
        (tournament_id,)
    ).fetchone()

    if tournament is None:
        connection.close()
        return "Turnier nicht gefunden", 404

    seating_format = tournament["format"]

    if is_top8_format(seating_format):
        seating_format = top8_game_format(seating_format)

    if seating_format not in {
        "Draft",
        "Sealed"
    }:
        connection.close()
        return (
            "Dieses Turnier benötigt keine Sitzordnung.",
            400
        )

    tournament_players = connection.execute(
        """
        SELECT
            p.id,
            p.name,
            tp.seat_number
        FROM tournament_players tp
        JOIN players p
            ON p.id = tp.player_id
        WHERE tp.tournament_id = ?
        ORDER BY
            CASE
                WHEN tp.seat_number IS NULL THEN 999999
                ELSE tp.seat_number
            END,
            p.name
        """,
        (tournament_id,)
    ).fetchall()

    connection.close()

    return render_template(
        "tournament_seating.html",
        tournament=tournament,
        tournament_players=tournament_players
    )

@tournaments.route(
    "/<int:tournament_id>/standings"
)
def standings(tournament_id):

    connection = get_connection()

    tournament = connection.execute(
        """
        SELECT
            t.*,
            s.name AS series_name
        FROM tournaments t
        LEFT JOIN tournament_series s
            ON s.id = t.series_id
        WHERE t.id = ?
        """,
        (tournament_id,)
    ).fetchone()

    if tournament is None:
        connection.close()
        return "Turnier nicht gefunden", 404


    players = connection.execute(
        """
        SELECT
            p.id,
            p.name

        FROM players p

        JOIN tournament_players tp
            ON tp.player_id = p.id

        WHERE tp.tournament_id = ?

        ORDER BY p.name
        """,
        (tournament_id,)
    ).fetchall()


    # -------------------------------------------------
    # Alle abgeschlossenen Matches dieses Turniers
    # -------------------------------------------------

    matches = connection.execute(
        """
        SELECT
            m.id,
            m.player1_id,
            m.player2_id,
            m.player1_games,
            m.player2_games,
            m.result

        FROM matches m

        JOIN rounds r
            ON r.id = m.round_id

        WHERE r.tournament_id = ?
          AND m.result IS NOT NULL
        """,
        (tournament_id,)
    ).fetchall()


    # -------------------------------------------------
    # Grundstatistiken für jeden Spieler berechnen
    # -------------------------------------------------

    player_stats = {}


    for player in players:

        player_stats[player["id"]] = {
            "id": player["id"],
            "name": player["name"],

            "points": 0,

            "wins": 0,
            "losses": 0,
            "draws": 0,

            "matches_played": 0,

            "games_won": 0,
            "games_lost": 0,

            "games_played": 0,

            "opponents": []
        }


    for match in matches:

        player1_id = match["player1_id"]
        player2_id = match["player2_id"]

        result = match["result"]


        # ---------------------------------------------
        # Bye
        # ---------------------------------------------

        if result == "bye":

            if player1_id in player_stats:

                stats = player_stats[player1_id]

                stats["points"] += 3
                stats["wins"] += 1
                stats["matches_played"] += 1

                stats["games_won"] += (
                    match["player1_games"] or 0
                )

                stats["games_lost"] += (
                    match["player2_games"] or 0
                )

                stats["games_played"] += (
                    (match["player1_games"] or 0)
                    +
                    (match["player2_games"] or 0)
                )

            continue


        # ---------------------------------------------
        # Spieler 1
        # ---------------------------------------------

        if player1_id in player_stats:

            stats = player_stats[player1_id]

            stats["matches_played"] += 1

            stats["games_won"] += (
                match["player1_games"] or 0
            )

            stats["games_lost"] += (
                match["player2_games"] or 0
            )

            stats["games_played"] += (
                (match["player1_games"] or 0)
                +
                (match["player2_games"] or 0)
            )

            if player2_id in player_stats:

                stats["opponents"].append(
                    player2_id
                )


        # ---------------------------------------------
        # Spieler 2
        # ---------------------------------------------

        if player2_id in player_stats:

            stats = player_stats[player2_id]

            stats["matches_played"] += 1

            stats["games_won"] += (
                match["player2_games"] or 0
            )

            stats["games_lost"] += (
                match["player1_games"] or 0
            )

            stats["games_played"] += (
                (match["player1_games"] or 0)
                +
                (match["player2_games"] or 0)
            )

            if player1_id in player_stats:

                stats["opponents"].append(
                    player1_id
                )


        # ---------------------------------------------
        # Matchpunkte
        # ---------------------------------------------

        if result == "win1":

            if player1_id in player_stats:
                player_stats[player1_id]["points"] += 3
                player_stats[player1_id]["wins"] += 1

            if player2_id in player_stats:
                player_stats[player2_id]["losses"] += 1


        elif result == "win2":

            if player2_id in player_stats:
                player_stats[player2_id]["points"] += 3
                player_stats[player2_id]["wins"] += 1

            if player1_id in player_stats:
                player_stats[player1_id]["losses"] += 1


        elif result == "draw":

            if player1_id in player_stats:
                player_stats[player1_id]["points"] += 1
                player_stats[player1_id]["draws"] += 1

            if player2_id in player_stats:
                player_stats[player2_id]["points"] += 1
                player_stats[player2_id]["draws"] += 1


    # -------------------------------------------------
    # Tiebreaker berechnen
    # -------------------------------------------------

    for stats in player_stats.values():

        # ---------------------------------------------
        # Match-Win %
        #
        # Matchpunkte / maximal mögliche Matchpunkte
        # Mindestwert 33 %
        # ---------------------------------------------

        if stats["matches_played"] > 0:

            match_win_percentage = (
                stats["points"]
                /
                (3 * stats["matches_played"])
            )

        else:

            match_win_percentage = 0


        match_win_percentage = max(
            match_win_percentage,
            0.33
        )


        # ---------------------------------------------
        # Game-Win %
        #
        # Games gewonnen / (3 * Games gespielt)
        # Mindestwert 33 %
        # ---------------------------------------------

        if stats["games_played"] > 0:

            game_win_percentage = (
                stats["games_won"]
                /
                stats["games_played"]
            )

        else:

            game_win_percentage = 0


        game_win_percentage = max(
            game_win_percentage,
            0.33
        )


        stats["match_win_percentage"] = (
            match_win_percentage
        )

        stats["game_win_percentage"] = (
            game_win_percentage
        )


    # -------------------------------------------------
    # Opponent Match-Win % und
    # Opponent Game-Win % berechnen
    # -------------------------------------------------

    for stats in player_stats.values():

        opponent_match_percentages = []
        opponent_game_percentages = []


        for opponent_id in stats["opponents"]:

            if opponent_id not in player_stats:
                continue


            opponent = player_stats[opponent_id]


            opponent_match_percentages.append(
                opponent["match_win_percentage"]
            )


            opponent_game_percentages.append(
                opponent["game_win_percentage"]
            )


        # ---------------------------------------------
        # Opponent Match-Win %
        # ---------------------------------------------

        if opponent_match_percentages:

            opponent_match_win_percentage = (
                sum(opponent_match_percentages)
                /
                len(opponent_match_percentages)
            )

        else:

            opponent_match_win_percentage = 0


        # ---------------------------------------------
        # Opponent Game-Win %
        # ---------------------------------------------

        if opponent_game_percentages:

            opponent_game_win_percentage = (
                sum(opponent_game_percentages)
                /
                len(opponent_game_percentages)
            )

        else:

            opponent_game_win_percentage = 0


        stats["opponent_match_win_percentage"] = (
            opponent_match_win_percentage
        )

        stats["opponent_game_win_percentage"] = (
            opponent_game_win_percentage
        )


    # -------------------------------------------------
    # Liste für Template
    # -------------------------------------------------

    standings = list(
        player_stats.values()
    )


    # -------------------------------------------------
    # Offizielle Reihenfolge:
    #
    # 1. Match Points
    # 2. Opponent Match-Win %
    # 3. Game-Win %
    # 4. Opponent Game-Win %
    # -------------------------------------------------

    standings.sort(
        key=lambda player: (
            -player["points"],
            -player["opponent_match_win_percentage"],
            -player["game_win_percentage"],
            -player["opponent_game_win_percentage"],
            player["name"].lower()
        )
    )


    for index, player in enumerate(standings):

        player["rank"] = index + 1


    connection.close()


    return render_template(
        "tournament_standings.html",
        tournament=tournament,
        standings=standings
    )

@tournaments.route(
    "/<int:tournament_id>/start",
    methods=["POST"]
)
def start_tournament(tournament_id):

    connection = get_connection()


    tournament = connection.execute(
        """
        SELECT *
        FROM tournaments

        WHERE id = ?
        """,
        (tournament_id,)
    ).fetchone()


    if tournament is None:

        connection.close()

        return "Turnier nicht gefunden", 404


    if tournament["status"] != "planned":

        connection.close()

        return (
            "Dieses Turnier wurde bereits gestartet.",
            400
        )

    if is_top8_format(tournament["format"]):

        unfinished_series_tournament = connection.execute(
            """
            SELECT id
            FROM tournaments
            WHERE series_id = ?
              AND id != ?
              AND format NOT LIKE 'Top 8%'
              AND status != 'finished'
            LIMIT 1
            """,
            (
                tournament["series_id"],
                tournament_id
            )
        ).fetchone()

        if unfinished_series_tournament is not None:
            connection.close()
            return (
                "Die Top 8 kann erst gestartet werden, wenn alle "
                "anderen Turniere beendet sind.",
                400
            )


    players = connection.execute(
        """
        SELECT
            p.id,
            p.name,
            tp.seat_number

        FROM players p

        JOIN tournament_players tp
            ON tp.player_id = p.id

        WHERE tp.tournament_id = ?

        ORDER BY p.id
        """,
        (tournament_id,)
    ).fetchall()


    player_count = len(players)

    if (
        is_top8_format(tournament["format"])
        and player_count != 8
    ):

        connection.close()

        return (
            "Eine Top 8 benötigt genau acht Teilnehmer.",
            400
        )


    if player_count < 2:

        connection.close()

        return (
            "Ein Turnier benötigt mindestens "
            "2 Teilnehmer.",
            400
        )


    players = list(players)

    if is_top8_format(tournament["format"]):
        players.sort(key=lambda player: player["seat_number"])
    else:
        random.shuffle(players)


    # ==========================================
    # DRAFT / SEALED:
    # SITZPLÄTZE VERGEBEN
    # ==========================================

    if is_top8_format(tournament["format"]):

        seating_players = (
            players[:4]
            + list(reversed(players[4:]))
        )

        for index, player in enumerate(seating_players):

            connection.execute(
                """
                UPDATE tournament_players
                SET seat_number = ?
                WHERE tournament_id = ?
                  AND player_id = ?
                """,
                (
                    index + 1,
                    tournament_id,
                    player["id"]
                )
            )

        players = seating_players

    elif tournament["format"] in {
        "Draft",
        "Sealed"
    }:

        for index, player in enumerate(players):

            seat_number = index + 1

            connection.execute(
                """
                UPDATE tournament_players

                SET seat_number = ?

                WHERE tournament_id = ?
                  AND player_id = ?
                """,
                (
                    seat_number,
                    tournament_id,
                    player["id"]
                )
            )

    else:

        # Bei Constructed keine Sitzplatzlogik
        connection.execute(
            """
            UPDATE tournament_players

            SET seat_number = NULL

            WHERE tournament_id = ?
            """,
            (tournament_id,)
        )


    now = datetime.now().isoformat(
        timespec="seconds"
    )


    # ==========================================
    # TURNIER STARTEN
    # ==========================================

    connection.execute(
        """
        UPDATE tournaments

        SET
            status = 'running',
            current_round = 1

        WHERE id = ?
        """,
        (tournament_id,)
    )

    if tournament["series_id"] is not None:
        from routes.series import update_series_status
        update_series_status(
            connection,
            tournament["series_id"]
        )


    # ==========================================
    # RUNDE 1
    # ==========================================

    cursor = connection.execute(
        """
        INSERT INTO rounds
        (
            tournament_id,
            round_number,
            status,
            started_at
        )
        VALUES (?, 1, 'active', ?)
        """,
        (
            tournament_id,
            now
        )
    )


    round_id = cursor.lastrowid


    # ==========================================
    # DRAFT / SEALED
    #
    # Sitzplatz 1 gegen 1 + N/2
    # ==========================================

    if is_top8_format(tournament["format"]):

        create_single_elimination_pairings(
            connection,
            tournament_id,
            round_id
        )

    elif tournament["format"] in {
        "Draft",
        "Sealed"
    }:

        # Sitzplätze sind bereits vergeben.
        # Wir lesen sie in der Reihenfolge ein.

        seated_players = connection.execute(
            """
            SELECT
                p.id,
                p.name,
                tp.seat_number

            FROM tournament_players tp

            JOIN players p
                ON p.id = tp.player_id

            WHERE tp.tournament_id = ?

            ORDER BY tp.seat_number
            """,
            (tournament_id,)
        ).fetchall()


        # Bei ungerader Teilnehmerzahl
        # bekommt der letzte Spieler ein Bye.
        pair_count = len(seated_players) // 2


        for index in range(pair_count):

            player1 = seated_players[index]

            opponent_index = index + pair_count

            player2 = seated_players[opponent_index]


            connection.execute(
                """
                INSERT INTO matches
                (
                    round_id,
                    player1_id,
                    player2_id,
                    player1_games,
                    player2_games,
                    result,
                    table_number
                )
                VALUES (?, ?, ?, 0, 0, NULL, ?)
                """,
                (
                    round_id,
                    player1["id"],
                    player2["id"],
                    index + 1
                )
            )


        # Ungerade Anzahl:
        # letzter Sitzplatz bekommt Bye
        if len(seated_players) % 2 == 1:

            bye_player = seated_players[-1]

            connection.execute(
                """
                INSERT INTO matches
                (
                    round_id,
                    player1_id,
                    player2_id,
                    player1_games,
                    player2_games,
                    result,
                    table_number
                )
                VALUES (?, ?, NULL, 2, 0, 'bye', ?)
                """,
                (
                    round_id,
                    bye_player["id"],
                    pair_count + 1
                )
            )


    # ==========================================
    # CONSTRUCTED
    #
    # Zufällige Paarungen
    # ==========================================

    else:

        table_number = 1

        index = 0


        while index < len(players):

            player1 = players[index]


            if index + 1 >= len(players):

                connection.execute(
                    """
                    INSERT INTO matches
                    (
                        round_id,
                        player1_id,
                        player2_id,
                        player1_games,
                        player2_games,
                        result,
                        table_number
                    )
                    VALUES (?, ?, NULL, 2, 0, 'bye', ?)
                    """,
                    (
                        round_id,
                        player1["id"],
                        table_number
                    )
                )

                index += 1

                continue


            player2 = players[index + 1]


            connection.execute(
                """
                INSERT INTO matches
                (
                    round_id,
                    player1_id,
                    player2_id,
                    player1_games,
                    player2_games,
                    result,
                    table_number
                )
                VALUES (?, ?, ?, 0, 0, NULL, ?)
                """,
                (
                    round_id,
                    player1["id"],
                    player2["id"],
                    table_number
                )
            )


            table_number += 1
            index += 2


    connection.commit()
    connection.close()

    if (
        tournament["format"] in {"Draft", "Sealed"}
        or (
            is_top8_format(tournament["format"])
            and top8_game_format(tournament["format"])
            in {"Draft", "Sealed"}
        )
    ):

        return redirect(
            url_for(
                "tournaments.seating",
                tournament_id=tournament_id
            )
        )


    return redirect(
        url_for(
            "tournaments.tournament",
            tournament_id=tournament_id
        )
    )

def rebuild_future_rounds(
    connection,
    tournament_id,
    changed_round_number
):

    future_rounds = connection.execute(
        """
        SELECT
            r.id,
            r.round_number
        FROM rounds r
        WHERE r.tournament_id = ?
          AND r.round_number > ?
        ORDER BY r.round_number
        """,
        (
            tournament_id,
            changed_round_number
        )
    ).fetchall()

    rebuilt_rounds = []
    blocked_round = None

    for future_round in future_rounds:

        # Hat diese Runde bereits ein echtes Ergebnis?
        played_match = connection.execute(
            """
            SELECT m.id
            FROM matches m
            WHERE m.round_id = ?
              AND m.result IS NOT NULL
              AND m.result != 'bye'
            LIMIT 1
            """,
            (future_round["id"],)
        ).fetchone()

        if played_match is not None:

            blocked_round = future_round["round_number"]
            break

        # Noch keine Ergebnisse:
        # Paarungen komplett neu aufbauen.
        connection.execute(
            """
            DELETE FROM matches
            WHERE round_id = ?
            """,
            (future_round["id"],)
        )

        connection.execute(
            """
            UPDATE rounds
            SET
                status = 'active',
                finished_at = NULL
            WHERE id = ?
            """,
            (future_round["id"],)
        )

        create_pairings(
            connection,
            tournament_id,
            future_round["id"]
        )

        rebuilt_rounds.append(
            future_round["round_number"]
        )

    return rebuilt_rounds, blocked_round

# ---------------------------------------------------------------------------
# Ergebnis erfassen / bearbeiten
# ---------------------------------------------------------------------------
def _parse_int(value):
    """Wandelt einen Formularwert sicher in int um."""
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None
    
@tournaments.route(
    "/<int:tournament_id>/match/<int:match_id>/result",
    methods=["POST"],
)
def enter_match_result(tournament_id, match_id):

    player1_games_raw = request.form.get(
        "player1_games",
        "",
    ).strip()

    player2_games_raw = request.form.get(
        "player2_games",
        "",
    ).strip()

    edit_mode = (
        request.form.get("edit_mode") == "1"
    )

    connection = get_connection()

    match = connection.execute(
        """
        SELECT
            m.*,
            r.tournament_id,
            r.round_number,
            r.status AS round_status
        FROM matches m
        JOIN rounds r
            ON r.id = m.round_id
        WHERE m.id = ?
          AND r.tournament_id = ?
        """,
        (
            match_id,
            tournament_id,
        ),
    ).fetchone()

    if match is None:

        connection.close()

        return "Match nicht gefunden", 404

    # Bye kann nicht als normales Match bearbeitet werden.
    if match["result"] == "bye":

        connection.close()

        return redirect(
            url_for(
                "tournaments.tournament",
                tournament_id=tournament_id,
            )
        )

    # Bereits gespeichertes Ergebnis darf nur
    # im Bearbeitungsmodus verändert werden.
    if (
        match["result"]
        and not edit_mode
    ):

        connection.close()

        return redirect(
            url_for(
                "tournaments.tournament",
                tournament_id=tournament_id,
            )
        )

    # -------------------------------------------------
    # Spielstände aus Eingabefeldern lesen
    # -------------------------------------------------

    # Wenn beide Felder leer sind, weiterhin automatisch
    # 2:0 eintragen.
    #
    # Dadurch bleibt die bisherige Komfortfunktion erhalten.
    if (
        player1_games_raw == ""
        and player2_games_raw == ""
    ):

        player1_games = 2
        player2_games = 0

    else:

        player1_games = _parse_int(
            player1_games_raw
        )

        player2_games = _parse_int(
            player2_games_raw
        )

        # Beide Werte müssen Zahlen >= 0 sein.
        if (
            player1_games is None
            or player2_games is None
            or player1_games < 0
            or player2_games < 0
        ):

            connection.close()

            return redirect(
                url_for(
                    "tournaments.tournament",
                    tournament_id=tournament_id,
                    edit=1 if edit_mode else None,
                )
            )

    tournament = connection.execute(
        """
        SELECT
            format,
            series_id
        FROM tournaments
        WHERE id = ?
        """,
        (tournament_id,)
    ).fetchone()

    if (
        player1_games > 2
        or player2_games > 2
        or (
            player1_games == player2_games
            and player1_games not in (0, 1)
        )
    ):
        connection.close()
        return redirect(
            url_for(
                "tournaments.tournament",
                tournament_id=tournament_id,
                edit=1 if edit_mode else None
            )
        )

    if is_top8_format(tournament["format"]):

        valid_best_of_three = (
            max(player1_games, player2_games) == 2
            and min(player1_games, player2_games) <= 1
            and player1_games != player2_games
        )

        if not valid_best_of_three:
            connection.close()
            return redirect(
                url_for(
                    "tournaments.tournament",
                    tournament_id=tournament_id,
                    edit=1 if edit_mode else None
                )
            )

    # -------------------------------------------------
    # Match-Ergebnis bestimmen
    # -------------------------------------------------

    if player1_games > player2_games:

        calculated_result = "win1"

    elif player2_games > player1_games:

        calculated_result = "win2"

    else:

        calculated_result = "draw"

    changed_round_number = match["round_number"]

    # -------------------------------------------------
    # Ergebnis speichern
    # -------------------------------------------------

    connection.execute(
        """
        UPDATE matches
        SET
            player1_games = ?,
            player2_games = ?,
            result = ?
        WHERE id = ?
        """,
        (
            player1_games,
            player2_games,
            calculated_result,
            match_id,
        ),
    )

    # Eine geänderte abgeschlossene Runde
    # wird wieder aktiv.
    connection.execute(
        """
        UPDATE rounds
        SET
            status = 'active',
            finished_at = NULL
        WHERE id = ?
        """,
        (match["round_id"],),
    )

    # -------------------------------------------------
    # Zukünftige noch nicht gespielte Runden
    # neu aufbauen
    # -------------------------------------------------

    rebuilt_rounds = []
    blocked_round = None

    if edit_mode:

        rebuilt_rounds, blocked_round = (
            rebuild_future_rounds(
                connection,
                tournament_id,
                changed_round_number,
            )
        )

    # -------------------------------------------------
    # Gibt es bereits später gespielte Runden?
    # -------------------------------------------------

    later_played_round = connection.execute(
        """
        SELECT MAX(r.round_number) AS round_number
        FROM rounds r
        JOIN matches m
            ON m.round_id = r.id
        WHERE r.tournament_id = ?
          AND r.round_number > ?
          AND m.result IS NOT NULL
          AND m.result != 'bye'
        """,
        (
            tournament_id,
            changed_round_number,
        ),
    ).fetchone()

    if later_played_round["round_number"] is None:

        # Keine spätere Runde wurde bereits gespielt.
        # Das Turnier kann daher bei der geänderten
        # Runde fortgesetzt werden.
        connection.execute(
            """
            UPDATE tournaments
            SET
                status = 'running',
                current_round = ?
            WHERE id = ?
            """,
            (
                changed_round_number,
                tournament_id,
            ),
        )

    if tournament["series_id"] is not None:
        from routes.series import update_series_status
        update_series_status(
            connection,
            tournament["series_id"]
        )

    connection.commit()
    connection.close()

    return redirect(
        url_for(
            "tournaments.tournament",
            tournament_id=tournament_id,
            edit=1 if edit_mode else None,
            changed=1 if edit_mode else None,
        )
    )

def calculate_tournament_stats(connection, tournament_id):

    players = connection.execute(
        """
        SELECT
            p.id,
            p.name
        FROM players p
        JOIN tournament_players tp
            ON tp.player_id = p.id
        WHERE tp.tournament_id = ?
        """,
        (tournament_id,)
    ).fetchall()


    matches = connection.execute(
        """
        SELECT
            m.player1_id,
            m.player2_id,
            m.player1_games,
            m.player2_games,
            m.result
        FROM matches m
        JOIN rounds r
            ON r.id = m.round_id
        WHERE r.tournament_id = ?
          AND m.result IS NOT NULL
        """,
        (tournament_id,)
    ).fetchall()


    stats = {}

    for player in players:

        stats[player["id"]] = {
            "id": player["id"],
            "name": player["name"],
            "points": 0,
            "opponents": [],
            "has_received_bye": False
        }


    for match in matches:

        player1 = match["player1_id"]
        player2 = match["player2_id"]
        result = match["result"]


        # Bye

        if result == "bye":

            if player1 in stats:

                stats[player1]["points"] += 3
                stats[player1]["has_received_bye"] = True

            continue


        if player1 not in stats:
            continue

        if player2 not in stats:
            continue


        stats[player1]["opponents"].append(player2)
        stats[player2]["opponents"].append(player1)


        if result == "win1":

            stats[player1]["points"] += 3

        elif result == "win2":

            stats[player2]["points"] += 3

        elif result == "draw":

            stats[player1]["points"] += 1
            stats[player2]["points"] += 1


    return stats

def create_pairings(connection, tournament_id, round_id):

    tournament = connection.execute(
        """
        SELECT format
        FROM tournaments
        WHERE id = ?
        """,
        (tournament_id,)
    ).fetchone()

    if is_top8_format(tournament["format"]):
        create_single_elimination_pairings(
            connection,
            tournament_id,
            round_id
        )
    else:
        create_swiss_pairings(
            connection,
            tournament_id,
            round_id
        )


def create_single_elimination_pairings(
    connection,
    tournament_id,
    round_id
):

    round_number = connection.execute(
        """
        SELECT round_number
        FROM rounds
        WHERE id = ?
        """,
        (round_id,)
    ).fetchone()["round_number"]

    if round_number == 1:

        players = connection.execute(
            """
            SELECT player_id
            FROM tournament_players
            WHERE tournament_id = ?
            ORDER BY seat_number
            """,
            (tournament_id,)
        ).fetchall()

        seeded_pairs = [
            (players[0]["player_id"], players[4]["player_id"]),
            (players[1]["player_id"], players[5]["player_id"]),
            (players[2]["player_id"], players[6]["player_id"]),
            (players[3]["player_id"], players[7]["player_id"])
        ]

    else:

        previous_round = round_number - 1

        matches = connection.execute(
            """
            SELECT
                m.player1_id,
                m.player2_id,
                m.result
            FROM matches m
            JOIN rounds r
                ON r.id = m.round_id
            WHERE r.tournament_id = ?
              AND r.round_number = ?
            ORDER BY m.table_number
            """,
            (
                tournament_id,
                previous_round
            )
        ).fetchall()

        winners = []

        for match in matches:

            winner_id = (
                match["player1_id"]
                if match["result"] == "win1"
                else match["player2_id"]
            )
            winners.append(winner_id)

        seeded_pairs = [
            (winners[index], winners[index + 1])
            for index in range(0, len(winners), 2)
        ]

    for table_number, (player1_id, player2_id) in enumerate(
        seeded_pairs,
        start=1
    ):

        connection.execute(
            """
            INSERT INTO matches
            (
                round_id,
                player1_id,
                player2_id,
                player1_games,
                player2_games,
                result,
                table_number
            )
            VALUES (?, ?, ?, 0, 0, NULL, ?)
            """,
            (
                round_id,
                player1_id,
                player2_id,
                table_number
            )
        )


def create_swiss_pairings(
    connection,
    tournament_id,
    round_id
):

    stats = calculate_tournament_stats(
        connection,
        tournament_id
    )

    players = list(stats.values())

    players.sort(
        key=lambda player: (
            -player["points"],
            -player["wins"],
            player["name"].lower()
        )
    )

    if not players:
        return

    # Ungerade Spielerzahl:
    # niedrigster Punktestand ohne bisheriges Bye bekommt das Bye.
    bye_player = None

    if len(players) % 2 == 1:

        candidates = [
            player
            for player in reversed(players)
            if not player["received_bye"]
        ]

        if not candidates:
            candidates = list(reversed(players))

        bye_player = candidates[0]

        players.remove(bye_player)

        connection.execute(
            """
            INSERT INTO matches (
                round_id,
                player1_id,
                player2_id,
                player1_games,
                player2_games,
                result,
                table_number
            )
            VALUES (?, ?, NULL, 2, 0, 'bye', ?)
            """,
            (
                round_id,
                bye_player["player_id"],
                1
            )
        )

    table_number = 2 if bye_player else 1

    while players:

        player1 = players.pop(0)

        opponent_index = None

        # Erst Gegner mit gleicher Punktzahl
        # und ohne bisheriges Duell suchen.
        for index, player2 in enumerate(players):

            if player2["points"] != player1["points"]:
                continue

            if player2["player_id"] in player1["opponents"]:
                continue

            opponent_index = index
            break

        # Danach Gegner aus einer anderen
        # Punktgruppe suchen.
        if opponent_index is None:

            for index, player2 in enumerate(players):

                if player2["player_id"] in player1["opponents"]:
                    continue

                opponent_index = index
                break

        # Als allerletzte Möglichkeit:
        # Wiederholung zulassen.
        if opponent_index is None:

            opponent_index = 0

        player2 = players.pop(opponent_index)

        connection.execute(
            """
            INSERT INTO matches (
                round_id,
                player1_id,
                player2_id,
                player1_games,
                player2_games,
                result,
                table_number
            )
            VALUES (?, ?, ?, 0, 0, NULL, ?)
            """,
            (
                round_id,
                player1["player_id"],
                player2["player_id"],
                table_number
            )
        )

        table_number += 1




def calculate_tournament_stats(connection, tournament_id):

    players = connection.execute(
        """
        SELECT
            p.id,
            p.name
        FROM tournament_players tp
        JOIN players p
            ON p.id = tp.player_id
        WHERE tp.tournament_id = ?
        ORDER BY p.name
        """,
        (tournament_id,)
    ).fetchall()

    stats = {}

    for player in players:
        stats[player["id"]] = {
            "player_id": player["id"],
            "name": player["name"],
            "points": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "games_won": 0,
            "games_lost": 0,
            "opponents": [],
            "received_bye": False,
        }

    matches = connection.execute(
        """
        SELECT
            m.player1_id,
            m.player2_id,
            m.player1_games,
            m.player2_games,
            m.result
        FROM matches m
        JOIN rounds r
            ON r.id = m.round_id
        WHERE r.tournament_id = ?
          AND m.result IS NOT NULL
        ORDER BY r.round_number
        """,
        (tournament_id,)
    ).fetchall()

    for match in matches:

        player1 = match["player1_id"]
        player2 = match["player2_id"]

        if match["result"] == "bye":

            if player1 in stats:
                stats[player1]["points"] += 3
                stats[player1]["wins"] += 1
                stats[player1]["received_bye"] = True

            continue

        if player1 not in stats or player2 not in stats:
            continue

        stats[player1]["games_won"] += (
            match["player1_games"] or 0
        )

        stats[player1]["games_lost"] += (
            match["player2_games"] or 0
        )

        stats[player2]["games_won"] += (
            match["player2_games"] or 0
        )

        stats[player2]["games_lost"] += (
            match["player1_games"] or 0
        )

        stats[player1]["opponents"].append(player2)
        stats[player2]["opponents"].append(player1)

        if match["result"] == "win1":

            stats[player1]["points"] += 3
            stats[player1]["wins"] += 1

            stats[player2]["losses"] += 1

        elif match["result"] == "win2":

            stats[player2]["points"] += 3
            stats[player2]["wins"] += 1

            stats[player1]["losses"] += 1

        elif match["result"] == "draw":

            stats[player1]["points"] += 1
            stats[player2]["points"] += 1

            stats[player1]["draws"] += 1
            stats[player2]["draws"] += 1

    return stats

@tournaments.route(
    "/<int:tournament_id>/finish-round",
    methods=["POST"]
)
def finish_round(tournament_id):

    connection = get_connection()

    tournament = connection.execute(
        """
        SELECT *
        FROM tournaments
        WHERE id = ?
        """,
        (tournament_id,)
    ).fetchone()

    if tournament is None:
        connection.close()
        return "Turnier nicht gefunden", 404

    if tournament["status"] not in (
        "running",
        "finished"
    ):
        connection.close()
        return "Dieses Turnier kann nicht abgeschlossen werden.", 400

    current_round_number = tournament["current_round"]

    current_round = connection.execute(
        """
        SELECT *
        FROM rounds
        WHERE tournament_id = ?
          AND round_number = ?
        """,
        (
            tournament_id,
            current_round_number
        )
    ).fetchone()

    if current_round is None:
        connection.close()
        return "Aktuelle Runde nicht gefunden.", 400


    # -------------------------------------------------
    # Prüfen, ob noch Ergebnisse fehlen
    # -------------------------------------------------

    unfinished_match = connection.execute(
        """
        SELECT
            m.id,
            m.table_number
        FROM matches m
        WHERE m.round_id = ?
          AND m.result IS NULL
        LIMIT 1
        """,
        (current_round["id"],)
    ).fetchone()

    if unfinished_match is not None:

        connection.close()

        return redirect(
            url_for(
                "tournaments.tournament",
                tournament_id=tournament_id
            )
        )


    # -------------------------------------------------
    # Aktuelle Runde abschließen
    # -------------------------------------------------

    connection.execute(
        """
        UPDATE rounds
        SET
            status = 'finished',
            finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (current_round["id"],)
    )


    # -------------------------------------------------
    # Ist dies die letzte Runde?
    # -------------------------------------------------

    if current_round_number >= tournament["rounds"]:

        connection.execute(
            """
            UPDATE tournaments
            SET
                status = 'finished'
            WHERE id = ?
            """,
            (tournament_id,)
        )

        if tournament["series_id"] is not None:
            from routes.series import update_series_status
            update_series_status(
                connection,
                tournament["series_id"]
            )

        connection.commit()
        connection.close()

        return redirect(
            url_for(
                "tournaments.standings",
                tournament_id=tournament_id
            )
        )


    # -------------------------------------------------
    # Es gibt noch mindestens eine weitere Runde
    # -------------------------------------------------

    next_round_number = (
        current_round_number + 1
    )


    # -------------------------------------------------
    # Prüfen, ob diese Runde bereits existiert
    #
    # Das ist wichtig, wenn eine alte Runde nachträglich
    # bearbeitet wurde.
    # -------------------------------------------------

    next_round = connection.execute(
        """
        SELECT *
        FROM rounds
        WHERE tournament_id = ?
          AND round_number = ?
        """,
        (
            tournament_id,
            next_round_number
        )
    ).fetchone()


    if next_round is not None:

        # Die Runde existiert bereits.
        # Da wir sie gerade erneut aus der aktuellen
        # Wertung erzeugen wollen, löschen wir nur
        # ihre noch nicht gespielten Paarungen.

        played_match = connection.execute(
            """
            SELECT id
            FROM matches
            WHERE round_id = ?
              AND result IS NOT NULL
              AND result != 'bye'
            LIMIT 1
            """,
            (next_round["id"],)
        ).fetchone()


        if played_match is not None:

            # Sicherheit:
            # Eine bereits gespielte Runde darf niemals
            # durch "Runde abschließen" überschrieben
            # werden.

            connection.commit()
            connection.close()

            return redirect(
                url_for(
                    "tournaments.tournament",
                    tournament_id=tournament_id
                )
            )


        connection.execute(
            """
            DELETE FROM matches
            WHERE round_id = ?
            """,
            (next_round["id"],)
        )


        connection.execute(
            """
            UPDATE rounds
            SET
                status = 'active',
                finished_at = NULL,
                started_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (next_round["id"],)
        )


        next_round_id = next_round["id"]


    else:

        # Die nächste Runde existiert noch nicht.
        # Also neu anlegen.

        cursor = connection.execute(
            """
            INSERT INTO rounds (
                tournament_id,
                round_number,
                status,
                started_at
            )
            VALUES (
                ?,
                ?,
                'active',
                CURRENT_TIMESTAMP
            )
            """,
            (
                tournament_id,
                next_round_number
            )
        )

        next_round_id = cursor.lastrowid


    # -------------------------------------------------
    # Neue Swiss-Paarungen erzeugen
    # -------------------------------------------------

    create_pairings(
        connection,
        tournament_id,
        next_round_id
    )


    # -------------------------------------------------
    # Turnier auf die neue Runde setzen
    # -------------------------------------------------

    connection.execute(
        """
        UPDATE tournaments
        SET
            current_round = ?,
            status = 'running'
        WHERE id = ?
        """,
        (
            next_round_number,
            tournament_id
        )
    )

    if tournament["series_id"] is not None:
        from routes.series import update_series_status
        update_series_status(
            connection,
            tournament["series_id"]
        )

    connection.commit()
    connection.close()


    return redirect(
        url_for(
            "tournaments.tournament",
            tournament_id=tournament_id
        )
    )