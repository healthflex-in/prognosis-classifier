# Recommendation thinking-budget benchmark

## Summary (averaged across patients)

| Budget | Median latency (s) | Mean quality /100 |
|---|---|---|
| auto (baseline) | 7.16 | 52.3 |
| 256 (capped) | 2.51 | 100.0 |
| 128 (capped) | 1.76 | 100.0 |
| 0 (off) | 1.19 | 100.0 |

> Pick the lowest budget whose mean quality matches `auto (baseline)`.


---

## Patient 683da593e2467bc639419f35 — Abhishek Jaiswal
**Chief complaint:** pt C/O pain at the neck from 2 months, since he did a 90kg bench press. He wishes to continue his gym traning pain free.

| Budget | Median (s) | Min (s) | Quality /100 | Runs |
|---|---|---|---|---|
| auto (baseline) | 7.83 | 7.73 | 52.3 | [7.93, 7.73] |
| 256 (capped) | 2.36 | 2.25 | 100.0 | [2.25, 2.46] |
| 128 (capped) | 1.76 | 1.69 | 100.0 | [1.69, 1.84] |
| 0 (off) | 1.16 | 1.12 | 100.0 | [1.12, 1.2] |

### Output @ auto (baseline) — quality 52.3/100
_structure 30.0 · no_generic 0.0 · specificity 7.3 · distinct 10.0 · no_alarming 5.0_

- Reduce pain and restore comfortable movement
- Improve strength and physical function
- Build tolerance to activity and daily tasks

_Next session plan:_ We will begin hands-on treatment and targeted exercises in your next session.
  - ⚠️ generic/forbidden phrasing: 'Reduce pain and restore comfortable movement' (~'reduce pain and restore comfortable movement')
  - ⚠️ generic/forbidden phrasing: 'Improve strength and physical function' (~'improve strength and physical function')
  - ⚠️ generic/forbidden phrasing: 'Build tolerance to activity and daily tasks' (~'build tolerance to activity')
  - ⚠️ area 1 not anchored to this patient: 'Reduce pain and restore comfortable movement'
  - ⚠️ area 3 not anchored to this patient: 'Build tolerance to activity and daily tasks'
  - ⚠️ next_session_plan not anchored to this patient

### Output @ 256 (capped) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Improve neck comfort during bench press
- Increase thoracic spine movement for lifting
- Build overall strength for gym training

_Next session plan:_ We will work on your neck and upper back movement, and start gentle strengthening.

### Output @ 128 (capped) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Improve neck comfort during gym training
- Restore full neck movement for daily activities
- Build strength for pain-free bench pressing

_Next session plan:_ We'll work on your neck and upper back movement, and gentle strengthening.

### Output @ 0 (off) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Improve neck comfort during gym training
- Increase thoracic spine mobility for lifting
- Build neck strength for bench press

_Next session plan:_ We will work on your neck and mid-back mobility, and start gentle strengthening.


---

## Patient 683da595e2467bc639419f4d — Alok Agrawal
**Chief complaint:** Patient complains  of multiple joints aches and pain.bilateral heel pain,knee pain.LOW BACK ache while bending down, since many years. 4 years back took right knee MRI showed rt acl partial tear.MRI:shows dic bulge lower lumbar.

| Budget | Median (s) | Min (s) | Quality /100 | Runs |
|---|---|---|---|---|
| auto (baseline) | 7.07 | 6.77 | 52.3 | [6.77, 7.37] |
| 256 (capped) | 2.83 | 2.6 | 100.0 | [3.06, 2.6] |
| 128 (capped) | 1.56 | 1.45 | 100.0 | [1.45, 1.66] |
| 0 (off) | 1.28 | 1.22 | 100.0 | [1.22, 1.35] |

### Output @ auto (baseline) — quality 52.3/100
_structure 30.0 · no_generic 0.0 · specificity 7.3 · distinct 10.0 · no_alarming 5.0_

- Reduce pain and restore comfortable movement
- Improve strength and physical function
- Build tolerance to activity and daily tasks

_Next session plan:_ We will begin hands-on treatment and targeted exercises in your next session.
  - ⚠️ generic/forbidden phrasing: 'Reduce pain and restore comfortable movement' (~'reduce pain and restore comfortable movement')
  - ⚠️ generic/forbidden phrasing: 'Improve strength and physical function' (~'improve strength and physical function')
  - ⚠️ generic/forbidden phrasing: 'Build tolerance to activity and daily tasks' (~'build tolerance to activity')
  - ⚠️ area 1 not anchored to this patient: 'Reduce pain and restore comfortable movement'
  - ⚠️ area 3 not anchored to this patient: 'Build tolerance to activity and daily tasks'
  - ⚠️ next_session_plan not anchored to this patient

### Output @ 256 (capped) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Improve lower back comfort when bending down
- Reduce bilateral heel pain with daily activities
- Strengthen hip muscles for better balance

_Next session plan:_ We will start with gentle lower back mobility and hip strengthening exercises.

### Output @ 128 (capped) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Reduce low back ache when bending down
- Improve strength for both heels
- Increase right knee comfort and stability

_Next session plan:_ We will start with gentle low back movement and begin strengthening your heels.

### Output @ 0 (off) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Reduce bilateral heel pain with daily activities
- Improve knee comfort and stability for movement
- Ease lower back ache when bending down

_Next session plan:_ We'll work on your lower back mobility and begin gentle strengthening for your hips.


---

## Patient 683da595e2467bc639419f53 — Amit Tirpude
**Chief complaint:** came for injury prevention program ,runs half marathon started since 2 years ,last 2 months increased running training 5km/day, before 2km/dayhad B/L club foot corrected conservatively in childhoodaim is to prepare for upcoming half marathon event .

| Budget | Median (s) | Min (s) | Quality /100 | Runs |
|---|---|---|---|---|
| auto (baseline) | 6.87 | 6.29 | 52.3 | [6.29, 7.44] |
| 256 (capped) | 2.49 | 2.44 | 100.0 | [2.54, 2.44] |
| 128 (capped) | 1.82 | 1.82 | 100.0 | [1.82, 1.82] |
| 0 (off) | 1.18 | 1.06 | 100.0 | [1.3, 1.06] |

### Output @ auto (baseline) — quality 52.3/100
_structure 30.0 · no_generic 0.0 · specificity 7.3 · distinct 10.0 · no_alarming 5.0_

- Reduce pain and restore comfortable movement
- Improve strength and physical function
- Build tolerance to activity and daily tasks

_Next session plan:_ We will begin hands-on treatment and targeted exercises in your next session.
  - ⚠️ generic/forbidden phrasing: 'Reduce pain and restore comfortable movement' (~'reduce pain and restore comfortable movement')
  - ⚠️ generic/forbidden phrasing: 'Improve strength and physical function' (~'improve strength and physical function')
  - ⚠️ generic/forbidden phrasing: 'Build tolerance to activity and daily tasks' (~'build tolerance to activity')
  - ⚠️ area 1 not anchored to this patient: 'Reduce pain and restore comfortable movement'
  - ⚠️ area 3 not anchored to this patient: 'Build tolerance to activity and daily tasks'
  - ⚠️ next_session_plan not anchored to this patient

### Output @ 256 (capped) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Improve hip and ankle mobility for running
- Strengthen posterior chain for running endurance
- Balance knee strength for half marathon training

_Next session plan:_ We'll start with hip mobility and begin strengthening your posterior chain.

### Output @ 128 (capped) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Build running tolerance for half marathon
- Improve hip and ankle mobility
- Strengthen posterior chain and calf muscles

_Next session plan:_ We'll start with hip mobility and strengthening for your running.

### Output @ 0 (off) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Improve hip and ankle mobility for running
- Strengthen posterior chain for half marathon training
- Balance knee extensor strength for running

_Next session plan:_ We will start with hands-on work for your hip and ankle mobility.


---

## Patient 683da592e2467bc639419f22 — Aakash Raman Sinha
**Chief complaint:** patient complains of right knee pain and discomfort at lateral side of knee. Pain is tender in nature and constant. Aggravates while prolong standing and  running.also he wanted to get a full body assessment and running analysis.Has a half marathon on 6th oct 2024 and the next in jan 2025 (half)

| Budget | Median (s) | Min (s) | Quality /100 | Runs |
|---|---|---|---|---|
| auto (baseline) | 7.25 | 7.18 | 52.3 | [7.33, 7.18] |
| 256 (capped) | 2.53 | 2.5 | 100.0 | [2.5, 2.56] |
| 128 (capped) | 1.76 | 1.71 | 100.0 | [1.71, 1.81] |
| 0 (off) | 1.2 | 1.08 | 100.0 | [1.08, 1.32] |

### Output @ auto (baseline) — quality 52.3/100
_structure 30.0 · no_generic 0.0 · specificity 7.3 · distinct 10.0 · no_alarming 5.0_

- Reduce pain and restore comfortable movement
- Improve strength and physical function
- Build tolerance to activity and daily tasks

_Next session plan:_ We will begin hands-on treatment and targeted exercises in your next session.
  - ⚠️ generic/forbidden phrasing: 'Reduce pain and restore comfortable movement' (~'reduce pain and restore comfortable movement')
  - ⚠️ generic/forbidden phrasing: 'Improve strength and physical function' (~'improve strength and physical function')
  - ⚠️ generic/forbidden phrasing: 'Build tolerance to activity and daily tasks' (~'build tolerance to activity')
  - ⚠️ area 1 not anchored to this patient: 'Reduce pain and restore comfortable movement'
  - ⚠️ area 3 not anchored to this patient: 'Build tolerance to activity and daily tasks'
  - ⚠️ next_session_plan not anchored to this patient

### Output @ 256 (capped) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Reduce right knee pain during standing and running
- Improve hip strength and control for running
- Build ankle stability for better running mechanics

_Next session plan:_ We'll start with hands-on work for your right knee and begin hip strengthening.

### Output @ 128 (capped) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Reduce right knee pain during prolonged standing
- Improve right knee comfort for running
- Strengthen hip muscles for better running stability

_Next session plan:_ We'll start hands-on work for your right knee and begin hip strengthening exercises.

### Output @ 0 (off) — quality 100.0/100
_structure 30.0 · no_generic 25.0 · specificity 30.0 · distinct 10.0 · no_alarming 5.0_

- Reduce right knee pain during prolonged standing and running
- Improve left hip extension and internal rotation strength
- Increase overall hip and ankle strength for running

_Next session plan:_ We'll start with hands-on work for your right knee and begin hip strengthening.


---
