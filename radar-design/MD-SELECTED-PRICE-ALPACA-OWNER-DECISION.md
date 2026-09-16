# MD-SELECTED-PRICE — Alpaca owner decision

2026-09-16. The owner confirms:

- Radar has one user: the owner.
- A consolidated SIP price line delayed by at least 15 minutes is acceptable for the current product stage.
- Proceed with the free Alpaca Paper Only account path rather than selecting the stored-only renderer as the primary C1 outcome.

## Account readiness — 2026-09-16

The owner reports account setup complete. Mastermind verified only that `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` variable names are present in `C:/Users/michi/Desktop/CodingStuff/.env`; values were not read or printed. `MD-SELECTED-PRICE-ALPACA-VALIDATE-1` is READY for owner dispatch using the prepared prompt. No provider request has yet been made by Mastermind.

This is a product/account-path decision. It does not create an account, accept agreements on the owner's behalf, authorize a worker to handle credential values, activate a provider, or authorize implementation/deployment.

## Consequence

The stored-only renderer remains the runtime fallback, not the selected primary source path. The owner must create the free Alpaca Paper Only account, accept the applicable agreements and store the generated paper credentials locally without posting them in chat. After credential presence is confirmed, the next bounded assignment is `MD-SELECTED-PRICE-ALPACA-VALIDATE-1` using `radar-design/MD-SELECTED-PRICE-ALPACA-VALIDATE-1-PROMPT.md`.

That assignment validates the documentation-based assumptions with at most 12 provider requests and no implementation. C1 remains blocked until the validation passes and the Mastermind records a source-acceptance ruling.

Expected local secret names:

- `APCA_API_KEY_ID`
- `APCA_API_SECRET_KEY`

Store them in the project's existing private root `.env` mechanism. Never place values in planning artifacts, evidence, Git, terminal transcripts intended for sharing, or chat.
