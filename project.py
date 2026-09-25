import questionary
from rich.console import Console
from rich.panel import Panel
import importlib.util
import subprocess
import sys
import csv
from datetime import datetime
from mysql.connector import Error
import os
import gzip
import signal

console = Console()

def main():
    console.print(Panel("Backup My Database", title="DBackup", border_style="blue"))
    console.print(f"[red][WARNING][/red] YOU need to have the db installed at your system to be able to do the backup!")
    custom_style_fancy = questionary.Style([("highlighted", "bold"),])
    framework = questionary.select("What's your DB: ", choices=["MySQL", "PostgreSQL", "MongoDB"], pointer="->", show_selected=True, style=custom_style_fancy).ask()
    match framework:
        case "MySQL":
            mysql_backup()
        case "PostgreSQL":
            postgresql_backup()
        case "MongoDB":
            mongodb_backup()

def credentials():
    autocompletelist = []
    try:
        with open('autocomplete.csv', 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile);
            for row in reader:
                autocompletelist.append(row['host'])
                autocompletelist.append(row['user'])
    except FileNotFoundError:
        pass
    host = questionary.autocomplete("host: ", choices=autocompletelist).ask()
    user = questionary.autocomplete("user: ", choices=autocompletelist).ask()
    password = questionary.password("password: ").ask()
    database = questionary.autocomplete("database name: ", choices=autocompletelist).ask()
    try:
        with open('autocomplete.csv', mode='a', newline='', encoding="utf-8") as csvfile:
            fieldname = ['host', 'user', 'database']
            writer = csv.DictWriter(csvfile, fieldnames=fieldname)
            writer.writeheader()
            writer.writerow({'host': host, 'user': user, 'database': database})
    except FileNotFoundError:
        pass
    return {"host": host, "user": user, "password": password, "database": database}

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H%M%S");

def mysql_backup():
    install_connector("mysql")
    db = credentials()
    import mysql.connector
    from mysql.connector import Error
    try:
        with mysql.connector.connect(
                host=db["host"],
                user=db["user"],
                password=db["password"],
                database=db["database"]
        ) as connection:
            if connection.is_connected():
                console.print(f"[green]CONNECTED[/green] to database {db['database']}")

            start_backup = questionary.confirm("Initiate database backup? ").ask()
            if start_backup:
                timestamp = get_timestamp()
                backup_file = f"{db['database']}_backup_{timestamp}.sql.gz"

                env = os.environ.copy()
                env["MYSQL_PWD"] = db["password"]

                command = [
                    "mariadb-dump",
                    f"-h{db['host']}",
                    f"-u{db['user']}",
                    db['database']
                ]

                console.print("[yellow]Processing backup and compressing... Please wait.[/yellow]")

                with gzip.open(backup_file, "wt", encoding="utf-8") as f:
                    subprocess.run(command, env=env, stdout=f, check=True)

                console.print(f"[green]SUCCESS[/green] Compressed backup saved to [bold]{backup_file}[/bold]")

    except Error as e:
        console.print(f"[bold][red]FAIL[/bold][/red] connecting to the database {db['database']} error: {e}")
    except subprocess.CalledProcessError as e:
        if os.path.exists(backup_file):
            os.remove(backup_file)
        console.print(f"[bold][red]FAIL[/bold][/red] Backup process failed: {e}")

def postgresql_backup():
    install_connector("postgresql")
    import psycopg2
    from psycopg2 import OperationalError
    db = credentials()
    db['port'] = questionary.select("port: ", choices=["5432", "other"]).ask()
    if db['port'] == "other":
        db['port'] = questionary.text("port: ").ask()
    connexion = f"host={db['host']} dbname={db['database']} user={db['user']} password={db['password']} port={db['port']}"
    try:
        console.print("Connecting to PostgreSQL database")
        with psycopg2.connect(connexion) as conn:
            console.print(f"[green]CONNECTED[/green] to database {db['database']}")
            with conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone();
                console.print(f"PostgreSQL version: {version[0]}")
                command = [
                        "pg_dump",
                        f"-h{db['host']}",
                        f"-p{db['port']}",
                        f"-U{db['user']}",
                        f"-d{db['database']}"
                ]
                start_backup = questionary.confirm("start postgres backup: ").ask()
                if start_backup:
                    timestamp = get_timestamp()
                    file = f"{db['database']}_backup_{timestamp}"
                    console.print("Starting backup and compressing...")
                    with gzip.open(file, "wt", encoding="utf-8") as f:
                        subprocess.run(command, stdout=f, check=True)
                        console.print(f"[green]Backup Successully made.[/green]")
    except OperationalError as error:
        console.print(f"[red][bold]Error[/bold][/red] connecting to database {db['database']}")
    except (subprocess.CalledProcessError, OSError) as e:
        console.print(f"[bold][red]FAIL[/bold][/red]Backup process or compression failed: {e}")
        if file and os.path.exists(file):
            try:
                os.remove(file)
            except OSError:
                pass

def mongodb_backup():
    install_connector("mongodb")
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError
    file = None
    import re
    normal_uri = questionary.text("uri: ").ask()
    password = questionary.password("password: ").ask()
    uri = re.sub(r"<db_password>", password,normal_uri)
    database = questionary.text("database: ").ask()
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.server_info()
        console.print(f"[green]CONNECTED[/green] to MongoDB server")
        start_backup = questionary.confirm("Start backup: ").ask()
        if start_backup:
            timestamp = get_timestamp()
            file = f"{database}_mongobackup_{timestamp}"
            command = [
                    "mongodump",
                    f"--uri={uri}",
                    f"--db={database}",
                    "--archive"
            ]
            console.print("Starting backup and compressing...")
            with gzip.open(file, "wt", encoding="utf-8") as f:
                subprocess.run(command, stdout=f, check=True)
            console.print("[green]SUCCESS[/green] Backup and compression finished")
            client.close()
    except ServerSelectionTimeoutError as e:
        console.print(f"[bold][red]FAIL[/bold][/red] connecting to MongoDB: {e}")
    except (subprocess.CalledProcessError, OSError) as e:
        console.print(f"[bold][red]FAIL[/bold][/red] MongoDB backup process failed: {e}")
        if backup_file and os.path.exists(backup_file):
            try:
                os.remove(backup_file)
            except OSError:
                pass

def install_connector(package: str):
    connectors = {"mysql": "mysql-connector-python", "postgresql": "psycopg2-binary", "mongodb": "pymongo"}
    package_exists = importlib.util.find_spec(connectors[package])
    console.print(f"[orange]VERIFYING[/orange] if connector for {package} exist...")
    if package_exists == None:
        console.print(f"Package [bold]{package}[bold] not installed or not found installing now")
        result = subprocess.run([sys.executable, "-m", "pip", "install", connectors[package]], capture_output=True, text=True)
        if result.returncode == 0:
            console.print(f"[green]SUCCESS[/green] Connector for {package} succefully installed")
        else:
            console.print(f"[red]FAIL[/red] Fail installing connector for {package}")
            console.print(result.stderr)
            sys.exit(1)
    else:
        console.print(f"Package {connectors[package]} already installed. Proceding")

if __name__ == "__main__":
    main()
