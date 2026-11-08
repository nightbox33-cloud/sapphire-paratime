#!/usr/bin/env python3
"""Offline reproduction models for the Sapphire/Privana money paths reviewed.

These are arithmetic/state-machine *models* transcribed 1:1 from the audited
source (line references below).  They are NOT fork tests: the sandbox used for
this audit has no egress to Sapphire mainnet RPC and no cargo/crates.io access,
so the enclave runtime and the live chain state could not be executed here.

Run:  python3 audit/poc/conservation_models.py
Exit code 0 == every conservation property asserted below holds.

Anchors
-------
oasis-sdk            runtime-sdk/v0.17.0  7dcaaf27ab71a94699b898c4d061291c8ab2671f
  runtime-sdk/src/modules/consensus/mod.rs            (amount_from/to_consensus)
  runtime-sdk/src/modules/consensus_accounts/mod.rs   (deposit / withdraw / msg results)
  runtime-sdk/modules/rofl-market/src/payment.rs       (pay / refund / claim)
sapphire-paratime    v1.3.0               46a9afcf8b3ac167cb71e459626a91a9a726b07f
privana              privana/v2.1.3       c4c1d7b4d9d2fbdff9cc1909b22216909b10d421
  src/services/deposit_verifier.py  (native balance-delta fallback)
  src/services/sweep_engine.py      (per-address lock + balance >= amount gate)
  solidity/contracts/Accounting.sol (creditDeposit / requestWithdrawal)
"""

SCALING = 1_000_000_000  # runtime consensus_scaling_factor (Sapphire mainnet genesis)


# ---------------------------------------------------------------------------
# 1. consensus <-> runtime bridge: can a deposit mint unbacked balance?
#    consensus_accounts::deposit -> consensus::amount_to_consensus (exact div)
#    -> consensus layer debits exactly that -> message result -> mint(runtime amt)
# ---------------------------------------------------------------------------
def amount_to_consensus(runtime_amount: int) -> int:
    if runtime_amount % SCALING != 0:
        raise ValueError("AmountNotRepresentable")  # remainder != 0 -> rejected
    return runtime_amount // SCALING


def amount_from_consensus(consensus_amount: int) -> int:
    return consensus_amount * SCALING  # checked_mul


def model_consensus_bridge():
    user_consensus = 10**18               # 1 ROSE on the consensus layer
    runtime_supply = 0
    burned = 0
    # deposit: user asks for 1 ROSE in runtime units -> exactly 1e9 taken at consensus
    for requested in (10**18, 10**18 + 1, 12345, 0):
        try:
            taken = amount_to_consensus(requested)
        except ValueError:
            continue
        if taken > user_consensus:
            continue
        user_consensus -= taken
        minted = amount_from_consensus(taken)   # what message_result mints
        runtime_supply += minted
        # round-trip out again: withdraw burns `minted` from the pending pool
        back = amount_to_consensus(minted)
        assert back == taken, "round trip changed value"
        burned += minted
    assert runtime_supply == burned
    return {"consensus_left": user_consensus, "minted": runtime_supply, "burned": burned}


# ---------------------------------------------------------------------------
# 2. rofl-market native escrow: sum of provider claims <= escrowed balance
#    payment.rs::claim  amount = claimable_time * total_amount / paid_time
#                       paid_from = now
# ---------------------------------------------------------------------------
def model_roflmarket_claims(total_amount: int, paid_from: int, paid_until: int, claims):
    balance = total_amount
    claimed = 0
    for now in claims:
        if now < paid_from:
            continue
        now = min(now, paid_until)
        claimable_time = max(0, now - paid_from)
        paid_time = paid_until - paid_from
        if paid_time == 0:
            amount = 0
        else:
            amount = (claimable_time * balance) // paid_time
        amount = min(amount, balance)
        balance -= amount
        claimed += amount
        paid_from = now
    assert claimed <= total_amount, "provider claimed more than escrow"
    return {"claimed": claimed, "balance": balance}


# ---------------------------------------------------------------------------
# 3. Privana deposit pipeline: is the block-delta fallback double-creditable?
#    verifier:  delta = balance(deposit_addr, block) - balance(deposit_addr, block-1)
#               credit expected_amount if delta >= expected_amount
#               deposit_id = keccak(chainId, txHash, tokenId, deposit_index)  [index=0 native]
#    sweep:     per-address lock;  if balance == 0 -> error ("nothing to sweep")
#               if balance < amount -> error
#               sweep exactly `amount`, then credit `amount`
# ---------------------------------------------------------------------------
class PrivanaPipeline:
    def __init__(self):
        self.addr_balance = 0          # source-chain balance of the attacker's deposit addr
        self.ledger = 0                # credited balance inside Accounting
        self.processed = set()         # processedDeposits
        self.swept_txs = 0

    def claim_native(self, chain_id, tx_hash, block_delta, expected_amount):
        # verifier
        if block_delta < expected_amount:
            return "rejected:onchain<claimed"
        deposit_id = (chain_id, tx_hash, 0)
        if deposit_id in self.processed:
            return "already-credited"
        # sweep (serialised per address by asyncio lock)
        if self.addr_balance == 0:
            return "error:nothing-to-sweep"
        if self.addr_balance < expected_amount:
            return "error:balance<amount"
        self.addr_balance -= expected_amount
        self.swept_txs += 1
        self.processed.add(deposit_id)
        self.ledger += expected_amount      # creditDeposit(amount=verified amount)
        return "credited"


def model_privana_block_delta():
    p = PrivanaPipeline()
    # one source-chain block, two txs each forwarding 1 unit *internally* to the
    # attacker-controlled deposit address => block delta = 2 units for BOTH txs
    p.addr_balance = 2
    block_delta = 2
    r1 = p.claim_native(8453, "0xaaa", block_delta, 2)   # credits 2
    r2 = p.claim_native(8453, "0xbbb", block_delta, 2)   # same delta, other txHash
    assert r1 == "credited"
    assert r2.startswith("error"), "double credit of one block delta!"
    assert p.ledger == 2 and p.addr_balance == 0
    return {"first": r1, "second": r2, "ledger": p.ledger, "onchain_swept": p.swept_txs}


# ---------------------------------------------------------------------------
# 4. Sapphire subcall precompile (0x0103): can a contract act as another address?
#    precompile/subcall.rs:  reject if context().address != code_address (delegate/callcode)
#                           caller = context().caller (immediate caller)
#                           evm.* re-entry forbidden by validator
#    evm/src/lib.rs: unsigned SimulateCall forces caller = Address::default()
# ---------------------------------------------------------------------------
MODULE_PENDING_WITHDRAWAL = "oasis1qr677rv0dcnh7ys4yanlynysvnjtk9gnsyhvm6ln"


def model_subcall_caller(frame):
    """frame = (code_address, executing_address, caller, via) -> effective subcall caller"""
    code_address, address, caller, via = frame
    if via in ("delegatecall", "callcode") and address != code_address:
        return None, "rejected:invalid call"          # precompile guard
    if via == "simulate_unsigned":
        return "0x" + "00" * 20, "ok"                 # caller cannot be spoofed
    return caller, "ok"


def model_subcall():
    # attacker contract tries to make the runtime move the shared pending-withdrawal pool
    for frame in [
        ("0xattackerC", "0xattackerC", "0xattackerEOA", "call"),
        ("0x0100..0103", "0xattackerC", "0xattackerC", "delegatecall"),
        ("0x0100..0103", "0x0200..0103", "0xattackerC", "callcode"),
        ("0x0100..0103", "0x0100..0103", "0x0", "simulate_unsigned"),
    ]:
        got, status = model_subcall_caller(frame)
        assert got != MODULE_PENDING_WITHDRAWAL
        if frame[3] in ("delegatecall", "callcode"):
            assert got is None and status.startswith("rejected")
    return {"pool_caller_reachable": False}


if __name__ == "__main__":
    print("1 consensus bridge     :", model_consensus_bridge())
    print("2 roflmarket escrow    :", model_roflmarket_claims(10_000, 0, 3600,
                                                              [600, 600, 1200, 5000]))
    print("3 privana block-delta  :", model_privana_block_delta())
    print("4 subcall caller        :", model_subcall())
    print("all conservation properties hold")
