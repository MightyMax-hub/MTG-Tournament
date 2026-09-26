from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for
)

from database.database import get_connection

import sqlite3


players = Blueprint(
    "players",
    __name__,
    url_prefix="/players"
)


@players.route("/")
def list_players():

    connection = get_connection()

    players = connection.execute(
        """
        SELECT
            p.id,
            p.name
        FROM players p
        WHERE p.active = 1
        ORDER BY p.name
        """
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
        WHERE m.result IS NOT NULL
        """
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
            "series_played": 0,
            "tournaments_played": 0,
            "opponents": []
        }
        for player in players
    }

    series_counts = connection.execute(
        """
        SELECT
            player_id,
            COUNT(*) AS series_played
        FROM series_players
        GROUP BY player_id
        """
    ).fetchall()

    tournament_counts = connection.execute(
        """
        SELECT
            player_id,
            COUNT(*) AS tournaments_played
        FROM tournament_players
        GROUP BY player_id
        """
    ).fetchall()

    for series_count in series_counts:

        player_id = series_count["player_id"]

        if player_id in player_stats:
            player_stats[player_id]["series_played"] = series_count[
                "series_played"
            ]

    for tournament_count in tournament_counts:

        player_id = tournament_count["player_id"]

        if player_id in player_stats:
            player_stats[player_id]["tournaments_played"] = tournament_count[
                "tournaments_played"
            ]

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

        if stats["matches_played"]:
            stats["match_win_percentage"] = max(
                stats["points"] / (3 * stats["matches_played"]),
                0.33
            )
        else:
            stats["match_win_percentage"] = 0

        if stats["games_played"]:
            stats["game_win_percentage"] = max(
                stats["games_won"] / stats["games_played"],
                0.33
            )
        else:
            stats["game_win_percentage"] = 0

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

    player_list = list(player_stats.values())

    player_list.sort(
        key=lambda player: (
            -player["points"],
            -player["opponent_match_win_percentage"],
            -player["game_win_percentage"],
            -player["opponent_game_win_percentage"],
            player["name"].lower()
        )
    )

    for index, player in enumerate(player_list):
        player["rank"] = index + 1

    connection.close()

    return render_template(
        "players.html",
        players=player_list
    )


@players.route("/new", methods=["GET", "POST"])
def new_player():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        if not name:

            return render_template(
                "player_form.html",
                error="Bitte einen Namen eingeben."
            )


        connection = get_connection()

        existing_player = connection.execute(
            """
            SELECT id
            FROM players

            WHERE name = ? COLLATE NOCASE
            """,
            (name,)
        ).fetchone()


        if existing_player:

            connection.close()

            return render_template(
                "player_form.html",
                error=(
                    "Dieser Spielername existiert bereits. "
                    "Bitte einen anderen Namen verwenden."
                )
            )


        try:

            connection.execute(
                """
                INSERT INTO players
                (
                    name
                )
                VALUES (?)
                """,
                (name,)
            )

            connection.commit()

        except sqlite3.IntegrityError:

            connection.close()

            return render_template(
                "player_form.html",
                error=(
                    "Dieser Spielername existiert bereits."
                )
            )


        connection.close()


        return redirect(
            url_for("players.list_players")
        )


    return render_template(
        "player_form.html"
    )
