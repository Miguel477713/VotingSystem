import os
import pyodbc

def check_db():
    print("Connecting to the Azure Database...")
    try:
        connectionString = os.environ["VOTING_SQL_CONNECTION_STRING"]
        conn = pyodbc.connect(connectionString)
        cursor = conn.cursor()

        print("\nVOTES:")
        cursor.execute("SELECT OptionCode, VoteCount FROM VoteOptions ORDER BY OptionCode")
        for row in cursor.fetchall():
            print(f"Option {row.OptionCode}: {row.VoteCount} votes")

        print("\nAUDIT LOGS:")
        cursor.execute("""
            SELECT TOP 10 EventType, UserId, OptionCode, Details 
            FROM VoteAuditEvents 
        """)
        for row in cursor.fetchall():
            userId = row.UserId if row.UserId else "N/A"
            option = row.OptionCode if row.OptionCode else "N/A"
            details = row.Details if row.Details else "N/A"
            print(f"[{row.EventType}] User: {userId} | Option: {option} | Details: {details}")

        conn.close()

    except Exception as e:
        print(f"Error connecting to the database: {e}")

if __name__ == "__main__":
    check_db()
