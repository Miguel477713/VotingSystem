# Voting System: Distributed Architecture & Workflow

## 1. System Overview
The VotingSystem is a **Distributed System** because it is designed to run across multiple physical or virtual machines, with different components communicating over a network (TCP/HTTP) to achieve a single goal: securely recording user votes. 

It consists of three main architectural tiers:
1. **The Client Interface**: `HTTPGateway.py` or `Client.py`.
2. **The Application Layer (Servers):** Multiple instances of `Server.py`.
3. **The Data Layer:** The central Azure SQL Database.

## 2. Is it Decentralized?
The system is **Distributed but NOT Decentralized**. 
* **Why it is Distributed:** Multiple backend servers (`"127.0.0.1", "169.254.236.20", "169.254.236.21"`) work together to handle incoming gateway traffic.
* **Why it is NOT Decentralized:** The system relies entirely on a single, centralized database (Azure SQL). There is no blockchain, peer-to-peer voting consensus, or distributed ledger. Complete control and truth live inside the Azure SQL database.

## 3. Primary vs. Backup Servers (Failover & Leadership)
To prevent two servers from writing conflicting votes simultaneously, the system uses a **Leader Election** pattern:
* Multiple `Server.py` instances can be running at the exact same time.
* Only **ONE** server is the "Primary" (The Leader). The rest are "Backups" (Standby).
* **How it works (`SqlLeadershipService.py`):** 
  * Every 3 seconds (`CHECK_INTERVAL_SECONDS`), every server checks a table in the database called `Leadership`.
  * The leader places a 10-second "lease" on the database saying "I am alive and in charge."
  * If the primary server crashes or loses internet, it stops renewing its lease. 
  * After 10 seconds, the database lease expires (`LeaseUntil < SYSUTCDATETIME()`).
  * **How they compete (Atomic "Test-and-Set" Operation):** The standby servers see the expiration and race to acquire the new lease by running exactly the same SQL command at the same time:
    ```sql
    UPDATE Leadership
    SET LeaderId = ?, LeaseUntil = DATEADD(SECOND, ?, SYSUTCDATETIME())
    WHERE ResourceName = ? AND LeaseUntil < SYSUTCDATETIME()
    ```
  * Because Azure SQL is an ACID-compliant relation database, it processes concurrent updates atomically. Even if 10 backups fire this exact `UPDATE` simultaneously, the database engine uses locking so that **only the first command to arrive actually modifies the row**. 
  * The server whose `cursor.rowcount == 1` knows it won the race and becomes the new Primary server automatically. The losers get `rowcount == 0` and stay as backups.

## 4. End-to-End Workflow Process
When a user casts a vote, the following distributed workflow takes place:

1. **User Action:** The user clicks "Votar A" on the gateway's webpage (`http://localhost:8080`).
2. **Gateway Routing (`HTTPGateway.py`):** 
   * The Gateway acts as a Load Balancer/Router.
   * It attempts to send the vote to the primary backend server it remembers.
   * *Gateway Failover:* If that TCP backend (`169.254.236.20:5050`) is unreachable or crashed, the Gateway automatically marks it as dead for 30 seconds (`backendFailureCooldownSeconds = 30`) and attempts to send the vote to the next available backend in its list.
3. **Server Validation (`Server.py`):** 
    * The connected server checks if it is currently the "Leader". If it isn't, it rejects the request (`ERR not_leader`) because only the Leader is allowed to write to the database.
4. **Database Transaction (`SqlVoteRepository.py`):**
    * The Leader server connects to Azure SQL.
    * It locks the user's row to prevent race conditions.
    * It checks if the user has already voted.
    * If valid, it increments the vote total and logs the secure Audit Event using an atomic SQL Transaction.
5. **Confirmation:** The server responds `OK vote_recorded` to the Gateway, which displays the text to the user's browser.
