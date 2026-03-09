from datetime import datetime
from typing import Optional

import pyodbc


class SqlLeadershipService:
    def __init__(self, connectionString: str, resourceName: str, leaseSeconds: int = 10) -> None:
        self.connectionString = connectionString
        self.resourceName = resourceName
        self.leaseSeconds = leaseSeconds

    def CreateConnection(self) -> pyodbc.Connection:
        return pyodbc.connect(self.connectionString, autocommit=False)

    def TryAcquireLeadership(self, serverId: str) -> bool:
        
        #Try to become leader only if the current lease is expired.

        #Returns True if this server became leader.
        #Returns False if another server already holds a valid lease.
        connection = self.CreateConnection()

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                UPDATE Leadership
                SET LeaderId = ?,
                    LeaseUntil = DATEADD(SECOND, ?, SYSUTCDATETIME())
                WHERE ResourceName = ?
                  AND LeaseUntil < SYSUTCDATETIME()
                """,
                serverId,
                self.leaseSeconds,
                self.resourceName
            )

            rowsUpdated = cursor.rowcount
            connection.commit()

            return rowsUpdated == 1

        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def RenewLeadership(self, serverId: str) -> bool:
        connection = self.CreateConnection()

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                UPDATE Leadership
                SET LeaseUntil = DATEADD(SECOND, ?, SYSUTCDATETIME())
                WHERE ResourceName = ?
                AND LeaderId = ?
                AND LeaseUntil >= SYSUTCDATETIME()
                """,
                self.leaseSeconds,
                self.resourceName,
                serverId
            )

            rowsUpdated = cursor.rowcount
            connection.commit()

            return rowsUpdated == 1

        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ReleaseLeadership(self, serverId: str) -> bool:
        #Release leadership only if this server currently owns it.

        #Returns True if released.
        #Returns False if this server was not the leader.
        connection = self.CreateConnection()

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                UPDATE Leadership
                SET LeaderId = 'NONE',
                    LeaseUntil = '2000-01-01T00:00:00'
                WHERE ResourceName = ?
                  AND LeaderId = ?
                """,
                self.resourceName,
                serverId
            )

            rowsUpdated = cursor.rowcount
            connection.commit()

            return rowsUpdated == 1

        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def GetCurrentLeader(self) -> tuple[str, datetime]:
        connection = self.CreateConnection()

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT LeaderId, LeaseUntil
                FROM Leadership
                WHERE ResourceName = ?
                """,
                self.resourceName
            )

            row = cursor.fetchone()
            if row is None:
                raise RuntimeError(f"Leadership row not found for resource {self.resourceName}")

            return row.LeaderId, row.LeaseUntil

        finally:
            connection.close()

    def IsLeader(self, serverId: str) -> bool:
        #True only if this server is the leader and the lease is still valid.
        connection = self.CreateConnection()

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT 1
                FROM Leadership
                WHERE ResourceName = ?
                  AND LeaderId = ?
                  AND LeaseUntil >= SYSUTCDATETIME()
                """,
                self.resourceName,
                serverId
            )

            row = cursor.fetchone()
            return row is not None

        finally:
            connection.close()