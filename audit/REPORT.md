# Auditoría ofensiva — Oasis Sapphire / Oasis Protocol Foundation

**Fecha:** 2026-11-08 · **Alcance:** stack Sapphire ParaTime (runtime SGX, SDK, precompiles, librerías
contrato, DeFi/escrow construido por la fundación) · **Rama:** `arena/6cd095d1-sapphire-paratime`

---

## 0. Veredicto

**No crítico live** en la superficie revisada.

No encontré ninguna ruta en la que un atacante **sin rol privilegiado**, partiendo del estado
desplegado, termine con más valor del que puso a costa de inventario ajeno. Cada hipótesis de
drenaje que construí murió contra un hecho concreto del código anclado (tabla §4, con `archivo:línea`
y el hecho que la mata). Los modelos de conservación reproducibles están en
`audit/poc/conservation_models.py` (offline, exit 0 = no se crea ni se duplica valor).

**Dos límites duros que impiden declarar cobertura completa** (y por tanto impiden un "no crítico"
en sentido absoluto):

1. **Sin egress a RPC de Sapphire mainnet desde este sandbox** (sólo `github.com`,
   `codeload/api.github.com`, `registry.npmjs.org`, `pypi.org`). No pude leer bytecode, storage ni
   balances live, ni ejecutar un fork test. Todo el anclaje es *repo + manifiestos de despliegue del
   propio repo*. **No hay inventario medido on-chain.**
2. **Repos privados de la org no visibles** (la API devolvió exactamente los 106 públicos;
   `type=private` → 0). Si existen repos privados de la fundación, **no están cubiertos**.

---

## 1. REQUISITO PREVIO — estado

### 1.1 Orgs / espacios enumerados

| Espacio | Resultado |
|---|---|
| `github.com/oasisprotocol` (org de la fundación) | **106 repos públicos** — todos clonados |
| `github.com/oasis-protocol` | HTTP 404 (no existe) |
| `github.com/oasis-network`, `github.com/oasis-foundation` | No son la fundación (0 repos, descripciones ajenas) |

### 1.2 Clonado

- **106/106 repos** clonados con historia completa, `fetch --all --tags` (todas las ramas y tags).
- **Submodules inicializados** en los 10 repos que los declaran (`docs`, `sapphire-paratime`,
  `rofl-price-oracle`, `demo-rofl-chatbot`, `explorer`, `rose-app`, `rofl-app`, `oasis-boot`,
  `wasm3-rs`, `demo-chat`, `erc-8004`) — todos `rc=0`.
- Inventario con commit HEAD exacto, ramas y nº de tags: **`audit/foundation-repos.tsv`** (106 filas).
- **Bloqueado / parcial:** `oasisprotocol/nexus` usa **Git LFS** y `git-lfs` no está instalado en el
  sandbox ⇒ sólo punteros, contenido LFS **no** descargado (declarado, no declarado cubierto).

### 1.3 Anclas de código usadas (commit/tag exacto)

| Componente | Ancla |
|---|---|
| Sapphire ParaTime runtime (**mainnet**) | `sapphire-paratime` **v1.3.0** = `46a9afcf8b3ac167cb71e459626a91a9a726b07f` (`version = "1.3.0"`, sin pre-release ⇒ build Mainnet) |
| SDK del runtime | `oasis-sdk` **`runtime-sdk/v0.17.0`** = `7dcaaf27ab71a94699b898c4d061291c8ab2671f` (pin de `runtime/Cargo.toml`) |
| Key manager | `keymanager-paratime` **v0.7.0** (pin v1.3.0) / HEAD clonado v0.7.1 = `729ec725bfe8c227ee3b1594c4afdcddfa3a5ed4` |
| Librería de contratos | `sapphire-contracts` 0.2.18 (`contracts/CHANGELOG.md`), `WrappedROSE.sol` idéntico en v1.3.0 y `main` |
| Consentimiento/nodo | `oasis-core` `master` = `3c3958f76fa1619e006a0e4d79e718aa93ad41b2` (release más reciente `v26.4`) |
| Privana (DeFi/accounting, mainnet) | `privana` **`privana/v2.1.3`** = `c4c1d7b4d9d2fbdff9cc1909b22216909b10d421` |
| Gateway JSON-RPC | `oasis-web3-gateway` HEAD `8107e81b4d5e8dc7638c1399599dc6527cb7d655` |
| EVs/Fork VM | `evm` `v0.39.1-oasis` = `13a30bfc1a10074f3f1676988aeb6ada76c65553` |

### 1.4 Mapa artefacto desplegado → repo / commit

| Artefacto live | Dirección / ID | Repo : ruta : commit | Verificado |
|---|---|---|---|
| Sapphire ParaTime (mainnet) | runtime id `000000000000000000000000000000000000000000000000f80306c9858e7279`, chain `0x5afe` (23294) | `sapphire-paratime:runtime/src/lib.rs@v1.3.0` + `oasis-sdk@runtime-sdk/v0.17.0` | ID y params en código; **binario desplegado no verificable (sin RPC)** |
| wROSE | `0x8Bc2B030b299964eEfb5e1e0b36991352E56D2D3` | `sapphire-paratime:contracts/contracts/WrappedROSE.sol@v1.3.0` (fuente en `docs/addresses.md`) | fuente; bytecode no |
| OPL Enclave/Endpoint (por-dApp) | librería | `contracts/contracts/opl/Endpoint.sol@v1.3.0` | fuente |
| Celer MessageBus (Sapphire) | `0x9Bb46D5100d2Db4608112026951c9C965b233f4D` | externo (Celer), cableado en `opl/Endpoint.sol` | fuente del cableado |
| Privana Accounting (proxy, **mainnet**) | `0x5f16C90a0F410AE4Cdb76d9964f5FFDDeE305876`; ROFL app `rofl1qpzsmmpdl68spwd5y37s5m8znafahna9hc28retn` | `privana:solidity/contracts/Accounting.sol@privana/v2.1.3` | fuente + manifiesto README; bytecode no |
| Privana (staging testnet) | `0x910CFfe4e8B27bc367F6E34D6D8e3C31DED68B6f` | idem | fuente |
| Multicall3 / CreateX / Safe Singleton / Band Oracle | `0xcA11…CA11`, `0xba5E…a5Ed`, `0x914d…43d7`, `0xDA7a…74C3` | **externos**, no fuente de la fundación | n/a (fuera de alcance) |
| Module accounts (runtime) | `oasis1qr677rv0dcnh7ys4yanlynysvnjtk9gnsyhvm6ln` (pending-withdrawal), `oasis1qzcdegtf7aunxr5n5pw7n5xs3u7cmzlz9gwmq49r` (pending-delegation), `oasis1qza6sddnalgzexk3ct30gqfvntgth5m4hsyywmff` (ROFL app stake pool) | `oasis-sdk@runtime-sdk/v0.17.0` | derivación determinista verificada |

---

## 2. Inventario ajeno que el código custodia (medido en fuente, no en cadena)

| Custodia | Quién puede moverlo | Respaldo / delta |
|---|---|---|
| ROSE nativo detrás de **wROSE** (`0x8Bc2…D2D3`) | sólo `deposit`/`withdraw` del propio dueño; `withdraw` quema antes de enviar | 1:1 `msg.value`, sin share math |
| Pool **pending-withdrawal** compartido (`oasis1qr677…`) | sólo el handler de `message_result` disparado por el layer de consenso | `transfer`→`burn`/refund por evento; el importe por evento está en el contexto del mensaje, no en storage escribible por el usuario |
| **ROFL app stake pool** (`oasis1qza6s…`) | `rofl.Create` (transfer in) / `rofl.Remove` (devuelve `cfg.stake` al admin) | `cfg.stake` inmutable tras creación; no hay slashing en runtime |
| **roflmarket** escrow por instancia (dirección derivada de `(provider,id)`) | `pay` del pagador; `claim`/`refund` por provider/admin/scheduler según estado | pro-rata sobre balance y tiempo |
| **Privana Accounting** `0x5f16…` (ledger) + wallets "encumbered" en cadenas origen | ledger: EIP-712 del usuario / locks por servicio / `creditDeposit` sólo ROFL; wallets origen: clave dentro del TEE | depósitos verificados off-chain por el TEE |

**TVL: no medido** (sin RPC). Cualquier cifra en $ sería inventada; no la incluyo.

---

## 3. Criterios aplicados

Los cuatro a la vez: bug concreto en código que corre live · permissionless · call graph/params reales
· PoC con unwind y PnL ≥ 0 a costa de terceros. Todo lo que falló un criterio se descartó (§5).

---

## 4. Hipótesis de drenaje probadas y el hecho que las mata

| # | Hipótesis (dónde) | Hecho que la mata |
|---|---|---|
| H1 | **wROSE** inflación vía `receive`/rounding (`WrappedROSE.sol`) | `_mint(msg.sender, msg.value)` y `_burn` antes de `transfer`; 1:1 sin shares; sin ruta para acuñar sin ROSE. Sin bug |
| H2 | **Puente consenso↔runtime** acuña sin respaldo (`consensus_accounts/mod.rs:188‑…`, `consensus/mod.rs:419‑441`) | `amount_to_consensus` **exige resto 0** (`checked_rem != 0 → AmountNotRepresentable`); `amount_from_consensus` es `checked_mul(1e9)`. El `mint` sólo ocurre en `message_result_withdraw`, disparado por mensaje del layer de consenso (no por usuario) y con el importe del contexto. Conservación exacta (modelo 1) |
| H3 | **subcall 0x0103** permite actuar como otra dirección / module account (`precompile/subcall.rs:41,73`) | `if context().address != code_address` ⇒ rechaza `delegatecall`/`callcode`; `caller = context().caller` (llamante inmediato); reentrada `evm.*` prohibida por `ForbidReentrancy`. No alcanzable `oasis1qr677…` (modelo 4) |
| H4 | **precompile ERC20** (`mint`/`burn`) acuña sobre el balance del módulo accounts | No cableado en Sapphire: `impl module_evm::Config { type AdditionalPrecompileSet = (); }` (`runtime/src/lib.rs:71`); el `AccountToken` sólo se instancia en tests; `mint/burn` van por `is_minting_allowed` |
| H5 | **Fee proxy ROFL** drena el stake de apps ajenas (`rofl/mod.rs:365‑375`, `resolve_payer`) | El payer se resuelve a la **cuenta de consenso del nodo** (`Address::from_consensus_pk`), no al pool; `cfg.stake` nunca se muta; el pool no se toca ⇒ `Remove` devuelve exactamente lo ingresado. Además exige firma de la RAK |
| H6 | **roflmarket** doble-claim / refund del escrow (`payment.rs:251‑321`) | `claim` es pro-rata sobre `balance` actual y avanza `paid_from = now` (segundo claim en el mismo timestamp ⇒ `claimable_time = 0` ⇒ 0). Cambio de admin exige `ensure_caller_is_instance_admin`; reentrada al módulo prohibida por `Validator`. Σclaims ≤ escrow (modelo 2) |
| H7 | **Privana crédito sin depósito** vía fallback de *block-delta* (`deposit_verifier.py:227‑233` + `sweep_engine.py:360‑377`) | El delta es por-address, pero el sweep **relee el balance** bajo lock por address: `balance == 0 → "nothing to sweep"`, `balance < amount → error`. Un mismo delta de bloque reclamado con 2 `txHash` distintos acredita una sola vez (modelo 3). Además `deposit_index` = `logIndex` real (ERC20) o 0 (nativo) ⇒ el `depositId` no se puede variar para un mismo log |
| H8 | **Privana emergency withdraw** roba el depósito ajeno (`Accounting.sol:284‑360`) | El slot se crea con `msg.sender` (`requestEmergencyWithdraw`) y el destino `toAddress` se fija ahí; `executeEmergencyWithdraw` **no** acepta destino, sólo `nonce/amount/gasPrice` ⇒ cualquiera puede empujar fondos **al destino elegido por la víctima**; el `signedTx` se devuelve sólo a quien llama |
| H9 | **Privana EIP-712** replay / substitución de parámetros (`EIP712SignatureVerifier.sol`) | La cuenta debitada es el **signer recuperado** (no un parámetro); nonces por operación chequeados antes de firmar+incrementar; dominio con `verifyingContract` y `salt = chainid`; `toAddress` sí está en `Transfer`/`Lock`/`TransferLocked`. `Withdraw` omite `toAddress` pero `Accounting.sol:962` fija `toAddress = userAddress` ⇒ sin efecto |
| H10 | Colisión **address etherum ↔ cuenta runtime / module account** (`types/address.rs:182`) | `Address::from_eth` = `hash(ctx_spec, ver, eth)[..20]` con primer byte de versión; las module accounts son `from_module(hash)`. No invertible ⇒ requiere preimagen de 160 bits para suplantar saldo ajeno |
| H11 | **ataque de simulación** para exfiltrar estado confidencial / firmar por el ROFL | Real pero **known issue documentado** (`docs/develop/security.md` "Simulation Attack") y mitigado por `UPUPSUpgradeable` (0.2.18). No es exploit nuevo. Además el caller en `eth_call` sin firmar es forzado a `Address::default()` (`evm/src/lib.rs:704`, "*The sender cannot be spoofed*"), así que `onlyROFLQuery` (msg.sender = `roflSignerAddress`) **no** se puede suplantar con `from` |
| H12 | **rofl-paymaster** (vault + pruebas Hashi) drenable | Sólo testnet según su propio README (`sapphire-testnet`, `base-sepolia`, `eth-sepolia`); sin TVL live ⇒ fuera por criterio |
| H13 | **OPL Endpoint/Host** se queda con fees / mensajes forjados | No custodia: el fee va directo a `messageBus`; `executeMessage` exige `msg.sender == messageBus` **y** `_sender == remote && _senderChainId == remoteChainId` |

---

## 5. Observaciones NO críticas (no cumplen los 4 criterios)

- **Privana `AuthToken`**: `Sapphire.encrypt/decrypt(_authTokenEncKey, nonce = 0, …)` reutiliza
  `(key, nonce)` en todos los tokens (Deoxys-II). Rompe confidencialidad sólo frente a quien
  **posea** ≥2 tokens (los propios): no da acceso a tokens ajenos ⇒ no drena.
- **Privana `resolveWithdrawal(uint256)`** es público e idempotente; el nonce del wallet encumbered
  se asigna en `requestWithdrawal` y uno no difundido bloquea los posteriores (liveness; recuperable
  por cualquiera difundiendo el tx firmado, que consume nonce aunque revierta). No es robo.
- **Fallback block-delta de Privana** es seguro *sólo porque* el sweep revalida el balance. Un refactor
  que acredite sin ese gate lo convierte en inflación de ledger (crítico). Lo dejo como *hardening*,
  no como hallazgo.
- **`_decodeReceiptDelegate`** usa offsets mágicos (`result[1]==0x66`, parse desde 8) en
  `Subcall.sol`: fragilidad de parser, sin movimiento de valor.

---

## 6. Cobertura y lo no cubierto

- **Revisado en profundidad:** runtime Sapphire (`runtime/src/lib.rs`: chain id, state version 7,
  params de core/accounts/consensus/consensus_accounts/rewards/rofl/roflmarket); SDK v0.17.0
  (`modules/accounts`, `consensus`, `consensus_accounts`, `evm` + precompiles `subcall`/`confidential`/
  `standard`/`erc20`, `rofl`, `rofl-market`); librería de contratos (`WrappedROSE`, `Subcall`,
  `Sapphire`, `Sapphire.sol` auth `SiweAuth`/`A13e`, OPL `Endpoint`); Privana mainnet (Accounting,
  EVM signer, EIP-712 verifier, SIWE auth, pipeline de depósitos/sweep en el TEE).
- **Clonado y fijado, revisión no exhaustiva:** `oasis-core` (consenso, staking/slashing, roothash,
  p2p, keymanager policy, rofl-node), `oasis-web3-gateway`, `cometbft`/`evm` (forks), `nexus`
  (además LFS no descargado), `opengsn` (fork archivado).
- **No reproducible aquí:** build SGX ORC y fork test contra mainnet (sin egress / sin `cargo`).
  El PoC incluido es analítico (modelos de conservación), no un test de fork.

## 7. Reproducir

```bash
git clone https://github.com/oasisprotocol/sapphire-paratime && cd sapphire-paratime
python3 audit/poc/conservation_models.py     # exit 0 = propiedades de conservación
column -t -s$'\t' audit/foundation-repos.tsv # 106 repos, HEAD exacto, ramas, tags
```
