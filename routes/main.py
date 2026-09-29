from flask import Blueprint, render_template

from database.database import get_connection


main = Blueprint("main", __name__)


@main.route("/")
def dashboard():

    connection = get_connection()

    tournaments = connection.execute(
        """
        SELECT
            t.*,
            s.name AS series_name
        FROM tournaments t
        LEFT JOIN tournament_series s
            ON s.id = t.series_id
        ORDER BY t.tournament_date DESC, t.id DESC
        """
    ).fetchall()

    series_list = connection.execute(
        """
        SELECT
            s.*,
            COUNT(DISTINCT t.id) AS tournament_count
        FROM tournament_series s
        LEFT JOIN tournaments t
            ON t.series_id = s.id
        GROUP BY s.id
        ORDER BY COALESCE(s.start_date, '') DESC, s.id DESC
        """
    ).fetchall()

    player_count = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM players
        WHERE active = 1
        """
    ).fetchone()["count"]

    connection.close()

    return render_template(
        "dashboard.html",
        tournaments=tournaments,
        series_list=series_list,
        player_count=player_count
    )
