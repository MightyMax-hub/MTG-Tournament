from flask import Flask

from config import SECRET_KEY
from database.database import init_database

from routes.main import main
from routes.players import players
from routes.tournaments import tournaments
from routes.series import series


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = SECRET_KEY

    init_database()

    app.register_blueprint(main)
    app.register_blueprint(players)
    app.register_blueprint(tournaments)
    app.register_blueprint(series)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
