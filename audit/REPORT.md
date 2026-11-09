# Auditoría ofensiva — Oasis Sapphire / Oasis Protocol Foundation

**Fecha:** 2026-11-08 · **Alcance:** stack Sapphire ParaTime (runtime SGX, SDK, precompiles, librerías
contrato, DeFi/escrow construido por la fundación) · **Rama:** `arena/6cd095d1-sapphire-paratime`

---

## 0. Veredicto

**No crítico live** en la superficie revisada.

No encontré ninguna ruta en la que un atacante **sin rol privilegiado**, partiendo del estado
desplegado, termine con más valor del que puso a costa de inventario ajeno. Cada hipótesis de
drenaje que construí murió contra un hecho concreto del código anclado (tabla §4 y ronda 2 en §4b,
con `archivo:línea` y el hecho que la mata). Los modelos de conservación reproducibles están en
`audit/poc/conservation_models.py` (offline, 5 modelos, exit 0 = no se crea ni se duplica valor).

Segunda ronda (misma fecha) sobre superficie que faltaba — `EarnManager`/`SwapManager` live,
API/onramp/webhooks de Privana, adaptador Hashi del ROFL Header Oracle y **deriva de versiones**
del SDK (`v0.17.0` pineado vs `v0.17.1` vs `main`): **8 hipótesis nuevas, 8 refutadas**; cero fixes
de seguridad publicados que el binario live no tenga. Lo único accionable es *hardening* (N1, §5).


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
| Privana DeFi services (Swap/Earn, live en Sapphire) | `privana-services` `master` = `2de4a559d692286f4db2bb77016f5e9e85672931` (2026‑11‑06) — `solidity/contracts/{SwapManager,EarnManager}.sol` |
| ROFL Header Oracle (adaptador Hashi) | `rofl-header-oracle` `master` = `1d1f14e2011fbf9b5670a0decf10a9a396ce9d33` — `contracts/contracts/hashi/adapters/Oasis/ROFLAdapter.sol` |
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

## 4b. Ronda 2 (2026‑11‑08): superficie nueva + deriva de versiones

Se amplió la revisión a dos repos del ecosistema que no estaban en la primera pasada
(`privana-services` = SwapManager/EarnManager live en Sapphire; `rofl-header-oracle` = adaptador
Hashi sobre ROFL) y al **diff de versiones** del SDK (¿existe un fix de seguridad publicado que el
binario live no tenga?). Nuevas hipótesis, todas refutadas:

| # | Hipótesis (dónde) | Hecho que la mata |
|---|---|---|
| H14 | **EarnManager**: inflación del primer depositante / donación (`privana-services@2de4a559`, `EarnManager.sol:59‑60,389`) | `totalAssets` sólo cambia por `deposit` (`+= amount`, y el depositante recibe shares) o `syncTotalAssets` (onlyPoolAdmin): **no hay donación permissionless** que infle `A`. Y el offset virtual (`VIRTUAL_SHARES=1e6`, `VIRTUAL_ASSETS=1`) con `deposit` redondeando **abajo** (`:389`) y `withdraw` **arriba** (`:446‑448`) hace el round‑trip siempre lossy para el atacante (**modelo 5**: profit máx. 0 wei, claim máx. sobre el seed 1 wei en todo el grid) |
| H15 | **EarnManager.deposit** acuña shares a un `toUser` **no** ligado a la firma (`:382‑392`) | La firma del depositante es `Transfer(toAddress=pool.poolAddress, tokenId, amount, nonce)` y sí liga destino y nonce (`EIP712SignatureVerifier.sol:146‑149,284‑287`); lo no ligado es sólo *quién recibe las shares*. Explotarlo exige **poseer la firma del depositante**, que en Sapphire viaja cifrada (envelope Deoxys‑II) ⇒ no permissionless. Queda como hardening (N1) |
| H16 | **EarnManager.withdraw** salida sin co‑firma / replay (`:419‑457`) | Exige dos firmas: el consentimiento `Withdraw(poolId,amount,nonce)` del usuario (signer recuperado, se queman **sus** shares, nonce por usuario `:439‑440`) **y** la `Transfer` firmada por la pool (la custodia el servicio, no el llamante). Un relay no puede sacar fondos ajenos ni sin la pool |
| H17 | **SwapManager.swap** redirección de la pata de salida / robo de la de entrada (`SwapManager.sol:46‑78`) | La salida es `transferBalance(user,…)` con la firma del LP sobre `toAddress=user` (ligado); la entrada es una `Transfer` del propio usuario al `liquidityProvider`. Las dos patas no son atómicas: el riesgo es que el servicio no pague la salida = **confianza/custodia**, no drenaje permissionless |
| H18 | **API HTTP de Privana** (`/earn/deposit|withdraw`, `/swap`; webhooks `/onramp/*/webhook` en `privana`) acredita sin pago | Los webhooks se verifican con firma HMAC del proveedor y son **log‑only** ("non‑authoritative observability signals", `privana:src/api/routes.py:1022‑1088`); y los endpoints de `privana-services:src/api/{earn.py:178,swap.py:46}` sólo **encolan** la orden; todo movimiento de valor acaba en las firmas on‑chain de H15‑H17 ⇒ una petición forjada no acredita nada |
| H19 | **Oráculo de firma en el TEE**: hacer que firme un tx arbitrario (`generateGasFundingTx`, `generateSweep*`) y drenar el gas tank | Las tres son `view` + `onlyROFLQuery` (msg.sender = `roflSignerAddress`) y el TEE construye **todos** los argumentos internamente (`accounting_contract.py:748‑807`); no hay endpoint que pase calldata del usuario a esas vistas |
| H20 | **ROFLAdapter (Hashi)** forja hashes de bloque y drena el puente (`rofl-header-oracle@1d1f14e2`, `ROFLAdapter.sol:33,38,55`) | `storeBlockHeader(s)` exige `msg.sender == chainReporters[chainId]`, y los reporters sólo se fijan con `onlyROFL` (`:95`). `proveAncestralBlockHashes` **sí** es permissionless (`BlockHashAdapter.sol:15`) pero autoverificante: exige `keccak256(header) == hash almacenado` y sólo escribe el `parentHash` autenticado (`:28`) ⇒ no se puede elegir el valor. Forjar exige la clave del reporter o el origen de la app = privilegiado |
| H21 | **Deriva de versiones**: ¿el binario live carece de un fix ya publicado? | `runtime-sdk/v0.17.0` (pineado) → `v0.17.1`: 8 commits, sólo wasm3‑rs 0.3.4 y toolchain/imagen (módulo `contracts`, que Sapphire **no** incluye). `v0.17.0` → `main` en módulos de dinero: lints, bumps de deps, `MAX_METADATA_PAIRS`; ningún fix de seguridad. `sapphire-paratime v1.3.0` → `main`: `MAX_CHECK_NONCE_FUTURE_DELTA`, `max_batch_gas`, keymanager 0.7.1 y contratos nuevos (no desplegados). **No hay parche pendiente que el live necesite** |

Comprobaciones puntuales adicionales (todas negativas):

- **Redondeo de undelegación** (`consensus_accounts/mod.rs:969‑975`): `shares * total_amount /
  total_shares` **trunca** y `take_undelegation` consume la cola ⇒ Σ acuñado ≤ liberado por consenso;
  el polvo queda sin acuñar (pérdida de dust para el usuario, nunca inflación).
- **Stake de provider / app**: el record se borra **antes** de transferir (`rofl-market/src/lib.rs:296‑334`,
  `rofl/mod.rs:363‑371`) y `ProviderUpdate` no toca `stake`; `ProviderRemove` exige
  `instances_count == 0` ⇒ un solo reembolso, imposible retirar stake dos veces.
- **Rewards** (`rewards/mod.rs:184`): paga desde `ADDRESS_REWARD_POOL` a `good_compute_entities()` del
  round result (comité) ⇒ ni permissionless ni acuña.
- **Origen ROFL** (`rofl/mod.rs:125‑128`): `get_origin_app()` = `state::get_endorser(tx_caller_public_key)`,
  es decir hay que ser endorser (RK/RAK Ed25519) registrado del app; las claves se serializan con su
  tipo ⇒ sin colisión secp256k1↔Ed25519 y sin suplantar `onlyROFL`.
- **Gas funding de Privana**: `GAS_FUNDING_AMOUNT_WEI` (0.02 ROSE en testnet) < `MIN_DEPOSIT` (0.05) y
  `__post_init__` exige `funding ≥ 65k · floor · 2` ⇒ aun inflando `baseFee`/gas price el depósito
  sigue siendo barrible; si no lo fuera, los fondos quedan en la deposit address (la clave la tiene el
  wallet encumbered, no el atacante) ⇒ griefing no monetizable.

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
- **N1 — `EarnManager.deposit` no liga `toUser`** (`privana-services@2de4a559`,
  `EarnManager.sol:382‑392`): la firma autentica *la transferencia* (importe, token, destino = pool,
  nonce) pero no *quién recibe las shares*; quien posea esa firma puede mintearlas a otra cuenta.
  No es crítico porque en Sapphire la firma sólo existe dentro del calldata cifrado (envelope
  Deoxys‑II) y no se emite en eventos; se convierte en robo real si un relayer/servicio la filtra o
  si el contrato se despliega en una cadena con calldata pública. Fix: incluir `toUser` en el
  typed‑data del depósito (p. ej. `Deposit(bytes32 poolId,address toUser,uint256 amount,uint256 nonce)`)
  firmado por el usuario, igual que ya hace `Withdraw`.
- **N2 — `SwapManager.swap` no es atómico respecto de la intención del usuario**: la pata de entrada
  (usuario → LP) y la de salida (LP → usuario) son firmas independientes; un fallo entre ambas deja el
  input en el LP y depende de que el servicio haga el refund (`refund:redeposit` en la máquina de
  estados). Es riesgo de custodia/confianza, no vector permissionless.

---

## 6. Cobertura y lo no cubierto

- **Revisado en profundidad:** runtime Sapphire (`runtime/src/lib.rs`: chain id, state version 7,
  params de core/accounts/consensus/consensus_accounts/rewards/rofl/roflmarket); SDK v0.17.0
  (`modules/accounts`, `consensus`, `consensus_accounts`, `evm` + precompiles `subcall`/`confidential`/
  `standard`/`erc20`, `rofl`, `rofl-market`); librería de contratos (`WrappedROSE`, `Subcall`,
  `Sapphire`, `Sapphire.sol` auth `SiweAuth`/`A13e`, OPL `Endpoint`); Privana mainnet (Accounting,
  EVM signer, EIP‑712 verifier, SIWE auth, pipeline de depósitos/sweep/gas‑tank/withdrawals en el TEE);
  **ronda 2:** `privana-services` (SwapManager, EarnManager, API de earn/swap/onramp y webhooks) y
  `rofl-header-oracle` (ROFLAdapter + `BlockHashAdapter.proveAncestralBlockHashes`), más el diff de
  versiones `v0.17.0 → v0.17.1 → main` del SDK y `v1.3.0 → main` de `sapphire-paratime`.
- **Clonado y fijado, revisión no exhaustiva:** `oasis-core` (consenso, staking/slashing, roothash,
  p2p, keymanager policy, rofl-node), `oasis-web3-gateway`, `cometbft`/`evm` (forks), `nexus`
  (además LFS no descargado), `opengsn` (fork archivado), resto del ecosistema Privana
  (`privana-services` más allá de los contratos y la API, `rofl-header-oracle` lado Python).
- **Fuera del criterio (no es código de la fundación ni custodia de la fundación):** el lado LiFi/Base
  del swap (`LiFi` como target externo con allowance del LP), Aave/Base, y el despliegue concreto de
  un puente Hashi en Sapphire (el adaptador revisado es de terceros y sólo es alcanzable con la clave
  del reporter o el origen del app).
- **No reproducible aquí:** build SGX ORC y fork test contra mainnet (sin egress / sin `cargo`).
  El PoC incluido es analítico (modelos de conservación), no un test de fork.

## 7. Reproducir

```bash
git clone https://github.com/oasisprotocol/sapphire-paratime && cd sapphire-paratime
python3 audit/poc/conservation_models.py     # 5 modelos, exit 0 = propiedades de conservación
column -t -s$'\t' audit/foundation-repos.tsv # 106 repos, HEAD exacto, ramas, tags
```

Ronda 2 (repos no fundacionales, fijados por commit):

```bash
git clone https://github.com/privana/privana-services   && git -C privana-services   checkout 2de4a559
git clone https://github.com/privana/rofl-header-oracle && git -C rofl-header-oracle checkout 1d1f14e2
# H14-H17: EarnManager.sol:59-60,382-392,446-456 / SwapManager.sol:52-78
# H18: privana:src/api/routes.py:1022-1088 (webhooks HMAC, log-only)
#      privana-services:src/api/{earn.py:178,swap.py:46} (sólo encolan)
# H20: hashi/adapters/Oasis/ROFLAdapter.sol:33,38,55,95 / hashi/adapters/BlockHashAdapter.sol:15,28
git -C oasis-sdk log --oneline runtime-sdk/v0.17.0..runtime-sdk/v0.17.1   # H21: 8 commits, sin fixes
```
