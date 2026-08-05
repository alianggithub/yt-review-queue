DIFF SUMMARY: DESIGN.md (v1) vs DESIGN-v2.md (v2)                           
                                                                                
    What v2 RETAINED from v1 (under different section names):                   
    - Architecture diagram → v2 §6 System Architecture                          
    - Multi-account design → v2 §7 Identity and Multiple Accounts                   - Telegram commands → v2 §5.1 Commands (expanded: added switch, queue <id>, choose, link, watched, wiki)                                                    
    - Matching algorithm → v2 §11 Matching Algorithm (expanded with confidence scoring)                                                                             - KB classification → v2 §12 Metadata and Classification
    - Wiki workflow → v2 §13 Wiki Workflow
    - Security → v2 §14 Security and Privacy                                        - Phased build plan → v2 §18 Phased Delivery (expanded from 6 to 7 phases, added Phase 0)                                                                   
    - OAuth enrollment → v2 §7.3 Enrollment                                     
     
    What v2 ADDED (not in v1):          
    - §2 Design Principles (6 principles including idempotency, ambiguity-as-dat
a)                                      
    - §3.2 Non-goals for first release
    - §4.2 Offset accuracy (exact vs estimated)              
    - §4.3 OAuth separation (two independent grants — big architectural change)
    - §5.2 Capture acknowledgement                                              
    - §5.3 Ambiguous result handling                                                - §8 Storage Model (9 normalized SQLite tables vs v1's flat CSV)
    - §10.1 Data Portability API as primary acquisition path (v1 only had Takeou
t)                                                                              
    - §11.2 Scoring and decision (confidence scoring, v1 had none)
    - §11.3 URL construction                                                    
    - §15 Reliability and Observability                                         
    - §16 Configuration (all tunables)                                          
    - §17 Implementation Layout (src/ structure)                                    - §19 Test Matrix
    - §20 Decisions Still Needed                                                
    - §21 Official References                                                   
    - §22-24 (my additions: review notes, task breakdown, changes log)

   What v2 DROPPED from v1:                                                    
    1. "What was NOT proven" section (§2 in v1) — the 4 implementation risks fro
m the prototype. These are partially covered by v2's §20 Decisions Still Needed, but the explicit prototype-risk framing is gone.
    2. "Failure Modes & Pitfalls" section (§11 in v1) — 9 specific failure scena
rios (stale Takeout, user sends priority before pressing play, two devices overl
apping, deleted clips, Takeout retention cap, Takeout format changes, voice transcription noise, multiple users same account, OAuth refresh token expiry). Some 
are covered implicitly in v2's §15 Reliability and §19 Test Matrix, but the explicit per-failure-mode walkthrough with mitigation strategies is gone.
    3. "Open Questions for User" section (§13 in v1) — 6 specific decisions need
ing user input (OAuth client, Takeout cadence, self-report mode, wiki auto-write
 threshold, storage path, single vs dedicated bot). v2's §20 covers some of thes
e as "Decisions Still Needed" but drops the self-report mode question and the si
ngle-vs-dedicated-bot question.
    4. "Per-Account Queue CSV" data model (§6 in v1) — replaced by the SQLite sc
hema (intentional upgrade, not a drop).
    5. "Dispatch Flow (proven in prototype)" detail (§5.2 in v1) — v2's §6 cover
s architecture but doesn't call out what was specifically proven vs not.
    6. "Asymmetric Tolerance" (§7.4 in v1) — the critical finding from the proto
type about tolerance windows being asymmetric. v2 §11 covers matching but doesn'
t explicitly call out this finding as "proven — critical."
    7. "Supporting Files" section (§6.3 in v1) — details about accounts.yaml, us
ers.yaml, per-account CSV files. Replaced by §16 Configuration but the file stru
cture detail is gone.
     
    The dropped sections 2 (Failure Modes) and 3 (Open Questions) are the most s
ignificant losses. 