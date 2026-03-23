# Last Commit Changes

## 1. Token-Based Verification (`Database.sql` & `SqlVoteRepository.py`)
- **Schema Update:** Added a new `VotingTokens` table to store valid tokens (`TokenId`) and their associated emails (`Database/Database.sql`).
- **Validation Logic:** Updated `SqlVoteRepository.py` to query the `VotingTokens` table when a user attempts to vote. If the provided `userId` is not found, the vote is rejected.
- **Audit Logging:** Implemented an audit event for rejected votes. If a vote fails due to an invalid token, a `VOTE_REJECT` event is inserted into the `VoteAuditEvents` table with the reason `invalid_token`.


