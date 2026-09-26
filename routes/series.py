from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for
)

from database.database import get_connection


series = Blueprint(
    "series",
    __name__,
    url_prefix="/series"
)


def update_series_status(connection, series_id):

    if series_id is None:
        return

    tournament_statuses = connection.execute(
        """
        SELECT status
        FROM tournaments
        WHERE series_id = ?
        """,
        (series_id,)
    ).fetchall()

    if not tournament_statuses:
        new_status = "planned"
    elif any(
        tournament["status"] == "running"
        for tournament in tournament_statuses
    ):
        new_status = "running"
    elif all(
        tournament["status"] == "finished"
        for tournament in tournament_statuses
    ):
        new_status = "finished"
    else:
        new_status = "planned"

    connection.execute(
        """
        UPDATE tournament_series
        SET status = ?
        WHERE id = ?
        """,
        (new_status, series_id)
    )


@series.route("/")
def list_series():

    connection = get_connection()

    series_list = connection.execute(
        """
        SELECT
            s.*,
            COUNT(DISTINCT t.id) AS tournament_count,
            COUNT(DISTINCT sp.player_id) AS player_count
        FROM tournament_series s

        LEFT JOIN tournaments t
            ON t.series_id = s.id

        LEFT JOIN series_players sp
            ON sp.series_id = s.id

        GROUP BY s.id

        ORDER BY
            COALESCE(s.start_date, '') DESC,
            s.id DESC
        """
    ).fetchall()

    connection.close()

    return render_template(
        "series.html",
        series_list=series_list
    )


@series.route("/new", methods=["GET", "POST"])
def new_series():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        start_date = request.form.get(
            "start_date",
            ""
        ).strip()

        end_date = request.form.get(
            "end_date",
            ""
        ).strip()

        if not name:

            return render_template(
                "series_form.html",
                error="Bitte einen Namen eingeben."
            )

        connection = get_connection()

        connection.execute(
            """
            INSERT INTO tournament_series
            (
                name,
                description,
                start_date,
                end_date
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                name,
                description,
                start_date or None,
                end_date or None
            )
        )

        connection.commit()
        connection.close()

        return redirect(
            url_for("series.list_series")
        )

    return render_template(
        "series_form.html"
    )


@series.route("/<int:series_id>")
def show_series(series_id):

    connection = get_connection()

    series_data = connection.execute(
        """
        SELECT *
        FROM tournament_series
        WHERE id = ?
        """,
        (series_id,)
    ).fetchone()

    if series_data is None:

        connection.close()

        return "Turnierserie nicht gefunden", 404

    tournaments = connection.execute(
        """
        SELECT *
        FROM tournaments
        WHERE series_id = ?

        ORDER BY
            tournament_date,
            id
        """,
        (series_id,)
    ).fetchall()

    series_players = connection.execute(
        """
        SELECT
            p.id,
            p.name
        FROM players p

        JOIN series_players sp
            ON sp.player_id = p.id

        WHERE sp.series_id = ?

        ORDER BY p.name
        """,
        (series_id,)
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
              FROM series_players
              WHERE series_id = ?
          )

        ORDER BY p.name
        """,
        (series_id,)
    ).fetchall()

    connection.close()

    return render_template(
        "series_detail.html",
        series=series_data,
        tournaments=tournaments,
        series_players=series_players,
        available_players=available_players
    )


def _series_standings(connection, series_id):

    players = connection.execute(
        """
        SELECT
            p.id,
            p.name
        FROM players p
        JOIN series_players sp
            ON sp.player_id = p.id
        WHERE sp.series_id = ?
        ORDER BY p.name
        """,
        (series_id,)
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
        JOIN tournaments t
            ON t.id = r.tournament_id
        WHERE t.series_id = ?
                    AND t.counts_for_top8 = 1
          AND m.result IS NOT NULL
        """,
        (series_id,)
    ).fetchall()

    player_stats = {
        player["id"]: {
            "id": player["id"],
            "name": player["name"],
            "points": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "matches_played": 0,
            "games_won": 0,
            "games_played": 0,
            "opponents": []
        }
        for player in players
    }

    for match in matches:

        player1_id = match["player1_id"]
        player2_id = match["player2_id"]
        result = match["result"]

        if result == "bye":

            if player1_id in player_stats:
                stats = player_stats[player1_id]
                stats["points"] += 3
                stats["wins"] += 1
                stats["matches_played"] += 1
                stats["games_won"] += match["player1_games"] or 0
                stats["games_played"] += (
                    (match["player1_games"] or 0)
                    + (match["player2_games"] or 0)
                )

            continue

        for player_id, own_games, opponent_games, opponent_id in (
            (
                player1_id,
                match["player1_games"],
                match["player2_games"],
                player2_id
            ),
            (
                player2_id,
                match["player2_games"],
                match["player1_games"],
                player1_id
            )
        ):

            if player_id not in player_stats:
                continue

            stats = player_stats[player_id]
            stats["matches_played"] += 1
            stats["games_won"] += own_games or 0
            stats["games_played"] += (
                (own_games or 0) + (opponent_games or 0)
            )

            if opponent_id in player_stats:
                stats["opponents"].append(opponent_id)

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

            for player_id in (player1_id, player2_id):

                if player_id in player_stats:
                    player_stats[player_id]["points"] += 1
                    player_stats[player_id]["draws"] += 1

    for stats in player_stats.values():

        stats["match_win_percentage"] = max(
            stats["points"] / (3 * stats["matches_played"]),
            0.33
        ) if stats["matches_played"] else 0

        stats["game_win_percentage"] = max(
            stats["games_won"] / stats["games_played"],
            0.33
        ) if stats["games_played"] else 0

    for stats in player_stats.values():

        opponents = [
            player_stats[opponent_id]
            for opponent_id in stats["opponents"]
            if opponent_id in player_stats
        ]

        if opponents:
            stats["opponent_match_win_percentage"] = sum(
                opponent["match_win_percentage"]
                for opponent in opponents
            ) / len(opponents)
            stats["opponent_game_win_percentage"] = sum(
                opponent["game_win_percentage"]
                for opponent in opponents
            ) / len(opponents)
        else:
            stats["opponent_match_win_percentage"] = 0
            stats["opponent_game_win_percentage"] = 0

    standings = list(player_stats.values())
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

    return standings


@series.route("/<int:series_id>/standings")
def standings(series_id):

    connection = get_connection()

    series_data = connection.execute(
        """
        SELECT *
        FROM tournament_series
        WHERE id = ?
        """,
        (series_id,)
    ).fetchone()

    if series_data is None:
        connection.close()
        return "Turnierserie nicht gefunden", 404

    standings = _series_standings(connection, series_id)
    connection.close()

    return render_template(
        "series_standings.html",
        series=series_data,
        standings=standings
    )


@series.route(
    "/<int:series_id>/top8",
    methods=["GET", "POST"]
)
def create_top8(series_id):

    connection = get_connection()

    series_data = connection.execute(
        """
        SELECT *
        FROM tournament_series
        WHERE id = ?
        """,
        (series_id,)
    ).fetchone()

    if series_data is None:
        connection.close()
        return "Turnierserie nicht gefunden", 404

    other_tournaments = connection.execute(
        """
        SELECT id, status
        FROM tournaments
        WHERE series_id = ?
          AND format NOT LIKE 'Top 8%'
        """,
        (series_id,)
    ).fetchall()

    error = None

    if not other_tournaments:
        error = "Für die Top 8 muss mindestens ein Turnier existieren."
    elif any(
        tournament["status"] != "finished"
        for tournament in other_tournaments
    ):
        error = (
            "Die Top 8 kann erst erstellt werden, wenn alle "
            "anderen Turniere beendet sind."
        )

    existing_top8 = connection.execute(
        """
        SELECT id
        FROM tournaments
        WHERE series_id = ?
          AND format LIKE 'Top 8%'
        LIMIT 1
        """,
        (series_id,)
    ).fetchone()

    if existing_top8 is not None:
        error = "Für diese Serie existiert bereits eine Top 8."

    standings = _series_standings(connection, series_id)

    if len(standings) < 8:
        error = "Für die Top 8 werden mindestens acht Spieler benötigt."

    seating_players = (
        standings[:4]
        + list(reversed(standings[4:8]))
    )

    selected_format = request.form.get(
        "format",
        "Draft"
    ).strip()

    if selected_format not in {
        "Draft",
        "Sealed",
        "Constructed"
    }:
        error = "Ungültiges Top-8-Format."

    if request.method == "POST" and error is None:

        name = request.form.get(
            "name",
            f"{series_data['name']} Top 8"
        ).strip()

        tournament_date = request.form.get(
            "date",
            ""
        ).strip()

        if not name or not tournament_date:
            error = "Bitte Name und Datum ausfüllen."
        else:
            cursor = connection.execute(
                """
                INSERT INTO tournaments
                (
                    series_id,
                    name,
                    format,
                    tournament_date,
                    rounds,
                    counts_for_top8
                )
                VALUES (?, ?, ?, ?, 3, 0)
                """,
                (
                    series_id,
                    name,
                    f"Top 8 {selected_format}",
                    tournament_date
                )
            )

            tournament_id = cursor.lastrowid

            for index, player in enumerate(standings[:8]):
                connection.execute(
                    """
                    INSERT INTO tournament_players
                    (
                        tournament_id,
                        player_id,
                        seat_number
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        tournament_id,
                        player["id"],
                        index + 1
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

    connection.close()

    return render_template(
        "top8_form.html",
        series=series_data,
        standings=standings[:8],
        seating_players=seating_players,
        selected_format=selected_format,
        error=error
    )


@series.route(
    "/<int:series_id>/add-player",
    methods=["POST"]
)
def add_player(series_id):

    player_id = request.form.get(
        "player_id",
        ""
    ).strip()

    if player_id:

        connection = get_connection()

        connection.execute(
            """
            INSERT OR IGNORE INTO series_players
            (
                series_id,
                player_id
            )
            VALUES (?, ?)
            """,
            (
                series_id,
                int(player_id)
            )
        )

        connection.commit()
        connection.close()

    return redirect(
        url_for(
            "series.show_series",
            series_id=series_id
        )
    )


@series.route(
    "/<int:series_id>/remove-player",
    methods=["POST"]
)
def remove_player(series_id):

    player_id = request.form.get(
        "player_id",
        ""
    ).strip()

    if player_id:

        connection = get_connection()

        connection.execute(
            """
            DELETE FROM series_players

            WHERE series_id = ?
              AND player_id = ?
            """,
            (
                series_id,
                int(player_id)
            )
        )

        connection.commit()
        connection.close()

    return redirect(
        url_for(
            "series.show_series",
            series_id=series_id
        )
    )
