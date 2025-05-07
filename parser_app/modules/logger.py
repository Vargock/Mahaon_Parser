import logging
import os

import datetime

# Import modules
from .utilities import get_db_connection


# Symbols for each logging level, used to add an icon to the log message
LOG_SYMBOLS = {
    "debug": "🐞",
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "❌",
    "critical": "💥",
}


def get_logger(session_id=None):
    """
    Sets up and returns a logger instance for a given session ID. This logger
    writes logs to a file in the 'logs' directory. If the directory doesn't
    exist, it is created.

    Args:
        session_id (str, optional): The session ID for creating unique log files. If
                                     None, the default logger is used.

    Returns:
        logger (logging.Logger): The configured logger instance.
    """
    # Create timestamp for easier sorting, set up log file path
    timestamp = datetime.datetime.now().strftime("%H.%M.%S")

    # Use session_id as logger name, or 'general' if None
    logger_name = session_id if session_id is not None else f"{timestamp}"
    logger = logging.getLogger(logger_name)

    # Prevent double logging if logger is reused
    if not logger.handlers:
        # Ensure the logs directory exists, create if doesn't
        os.makedirs("logs", exist_ok=True)

        # Create daily_folder (e.g., logs/2025-05-06)
        log_folder = datetime.datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join("logs", log_folder)
        os.makedirs(daily_dir, exist_ok=True)

        # Log file name based on session_id (or 'general')
        if logger_name == timestamp:
            log_filename = os.path.join(daily_dir, f"{logger_name}.log")
        else:
            log_filename = os.path.join(daily_dir, f"{timestamp}_{logger_name}.log")

        # Create a file handler to write logs to a file
        handler = logging.FileHandler(
            log_filename,
            encoding="utf-8",
        )

        # Define the log message format
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(filename)s - Line %(lineno)d - %(funcName)s: %(message)s"
        )

        # Set the format for the log handler
        handler.setFormatter(formatter)

        # Add the handler to the logger
        logger.addHandler(handler)

        # Set the log level for the logger to DEBUG, so all levels are captured
        logger.setLevel(logging.DEBUG)

        # Set the log level for the file handler to DEBUG, so all levels are captured
        handler.setLevel(logging.DEBUG)
    return logger


def save_log(session_id: str, message: str):
    """
    Saves the log message to a database, specifically the parse_logs table,
    which stores logs associated with a particular parsing session.

    Args:
        session_id (str): The current parsing session ID for logging.
        message (str): The log message to be saved.
    """
    if session_id is None:
        raise ValueError("session_id cannot be None for database logging")

    # Connect to the SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the session_id exists in the sessions table
    try:
        cursor.execute(
            "SELECT 1 FROM parse_sessions WHERE session_id = ?", (session_id,)
        )
    except Exception as e:
        log_message(session_id, f"Error logging: {e}", level="error")
    if cursor.fetchone() is None:
        # Handle the error or log a warning (you could raise an exception or handle it as needed)
        raise ValueError(f"Session ID {session_id} does not exist.")

    # Insert the log message into the database
    cursor.execute(
        """
        INSERT INTO parse_logs (session_id, log_message, timestamp)
        VALUES (:session_id, :log_message, :timestamp)
        """,
        {
            "session_id": session_id,
            "log_message": message,
            "timestamp": datetime.datetime.now().isoformat(" ", "minutes"),
        },
    )

    # Commit the transaction and close the connection
    conn.commit()
    conn.close()


def log_message(session_id: str, message: str, level: str = "info"):
    """
    Logs a message both to a file and to a database (if session_id is provided),
    adding a level-based symbol if needed.

    Args:
        session_id (str): The session ID used to identify the log source. If None,
                          logs only to a file (not to the database).
        message (str): The message to be logged.
        level (str, optional): The log level to use (e.g., "info", "error").
                               Defaults to "info".
    """
    # Retrieve the appropriate symbol based on the log level
    symbol = LOG_SYMBOLS.get(level.lower(), "")

    # Retrive the full message, strip it of whitespace
    full_message = message.strip()

    # Extract the first "word" to check if it’s an emoji
    first_word = full_message.split(maxsplit=1)[0] if full_message else ""

    if first_word not in LOG_SYMBOLS.values():
        # If not one of our symbols, check if it’s any emoji (Unicode heuristic)
        if not first_word or not (ord(first_word[0]) >= 0x1F300):
            # Add our emoji if no emoji or just plain text
            full_message = f"{symbol} {message}"

    # Get the logger for this session (or the default 'general' logger if session_id is None)
    logger = get_logger(session_id)

    # Save the message to the database only if session_id is provided
    if session_id is not None:
        save_log(session_id, full_message)

    # Use getattr to find the log method for the given level, defaulting to 'info'
    log_method = getattr(logger, level.lower(), logger.info)

    log_method(full_message)  # Log the full message at the specified log level

    print(full_message)
