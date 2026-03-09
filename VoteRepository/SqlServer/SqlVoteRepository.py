import json
from typing import List, Tuple

import pyodbc

from VoteRepositoryBase import VoteRepositoryBase


class SqlVoteRepository(VoteRepositoryBase):
    def __init__(self, options: List[str], connectionString: str) -> None:
        self.options = options
        self.connectionString = connectionString

        self.EnsureOptionsExist()

    def CreateConnection(self) -> pyodbc.Connection:
        connection = pyodbc.connect(self.connectionString, autocommit=False) #autocommit=False: To rally many SQL statements 
        return connection

    def EnsureOptionsExist(self) -> None:
        connection = self.CreateConnection()
        try:
            cursor = connection.cursor()

            for option in self.options:
                cursor.execute(
                    """
                    IF NOT EXISTS (
                        SELECT 1
                        FROM VoteOptions
                        WHERE OptionCode = ?
                    )
                    BEGIN
                        INSERT INTO VoteOptions (OptionCode, VoteCount)
                        VALUES (?, 0)
                    END
                    """,
                    option,
                    option
                )

            connection.commit() #SQL TRANSACTION
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def Audit(self, eventType: str, userId: str | None = None, option: str | None = None, details: str | None = None) -> None:
        connection = self.CreateConnection()

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO VoteAuditEvents
                (EventType, UserId, OptionCode, Details)
                VALUES (?, ?, ?, ?)
                """,
                eventType,
                userId,
                option,
                details
            )

            connection.commit() #SQL transaction

        finally: #always runs
            connection.close()

    def LoadLog(self) -> None:
        # With SQL, the database is the source of truth.
        # No need to restore in RAM
        return

    def GetSnapshotResults(self) -> str:
        connection = self.CreateConnection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT OptionCode, VoteCount
                FROM VoteOptions
                ORDER BY OptionCode
                """
            )

            voteCountsByOption = {option: 0 for option in self.options}
            for row in cursor.fetchall():
                voteCountsByOption[row.OptionCode] = row.VoteCount

            parts = [
                f"{option}={voteCountsByOption.get(option, 0)}"
                for option in self.options
            ]
            return "RESULTS " + " ".join(parts)
        finally:
            connection.close()

    def TryRecordVote(self, userId: str, option: str) -> Tuple[bool, str]:
        connection = self.CreateConnection()

        try:
            cursor = connection.cursor()

            # Lock the user row range logically by checking under transaction.
            #UPDLOCK: I may update update this row soon
            #HOLDLOCK: HOLD lock until transaction commits or rollback 
            cursor.execute(
                """
                SELECT 1
                FROM Votes WITH (UPDLOCK, HOLDLOCK)
                WHERE UserId = ?
                """,
                userId
            )
            existingVote = cursor.fetchone()
            
            
            #With placeholders VALUES (?, ?, ?, ?), the driver sends the values separately from the SQL command.
            #So the database treats them strictly as data, not executable SQL.
            #Prevents SQL injection
            if existingVote is not None:
                cursor.execute(
                    """
                    INSERT INTO VoteAuditEvents (EventType, UserId, OptionCode, Details)
                    VALUES (?, ?, ?, ?)
                    """,
                    "VOTE_REJECT",
                    userId,
                    option,
                    "already_voted"
                )
                connection.commit()
                return False, "already_voted"

            cursor.execute(
                """
                INSERT INTO Votes (UserId, OptionCode)
                VALUES (?, ?)
                """,
                userId,
                option
            )

            cursor.execute(
                """
                UPDATE VoteOptions
                SET VoteCount = VoteCount + 1
                WHERE OptionCode = ?
                """,
                option
            )

            cursor.execute(
                """
                INSERT INTO VoteAuditEvents (EventType, UserId, OptionCode, Details)
                VALUES (?, ?, ?, ?)
                """,
                "VOTE_ACCEPT",
                userId,
                option,
                "vote_recorded"
            )

            connection.commit()
            return True, "vote_recorded"

        except pyodbc.IntegrityError:
            connection.rollback()
            return False, "already_voted"
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()