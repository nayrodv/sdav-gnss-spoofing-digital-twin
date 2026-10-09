from pathlib import Path
import json, math
import pandas as pd
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parent; R=ROOT/'results'; F=ROOT/'figures'
OUT=ROOT/'SDAV_GNSS_Spoofing_Executed_PoC_Report.docx'

def set_cell_shading(cell, fill='E7E6E6'):
    tcPr=cell._tc.get_or_add_tcPr(); shd=OxmlElement('w:shd'); shd.set(qn('w:fill'),fill); tcPr.append(shd)

def add_table(doc, headers, rows, widths=None, font_size=8):
    table=doc.add_table(rows=1, cols=len(headers)); table.alignment=WD_TABLE_ALIGNMENT.CENTER; table.style='Table Grid'
    hdr=table.rows[0].cells
    for i,h in enumerate(headers):
        hdr[i].text=str(h); set_cell_shading(hdr[i]); hdr[i].vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for run in hdr[i].paragraphs[0].runs: run.font.bold=True; run.font.size=Pt(font_size)
    for row in rows:
        cells=table.add_row().cells
        for i,v in enumerate(row):
            cells[i].text='' if v is None or (isinstance(v,float) and math.isnan(v)) else str(v)
            cells[i].vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for p in cells[i].paragraphs:
                for run in p.runs: run.font.size=Pt(font_size)
    if widths:
        for row in table.rows:
            for i,w in enumerate(widths): row.cells[i].width=Inches(w)
    doc.add_paragraph()
    return table

def add_caption(doc,text):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(text); r.italic=True; r.font.size=Pt(9)

def add_bullet(doc,text):
    p=doc.add_paragraph(text,style='List Bullet'); p.paragraph_format.space_after=Pt(2); return p

info=json.load(open(R/'trained_detector_parameters.json'))
det=pd.read_csv(R/'detection_confidence_intervals.csv')
scen=pd.read_csv(R/'detection_by_scenario.csv')
stress=pd.read_csv(R/'stress_test_summary.csv')
resp=pd.read_csv(R/'response_summary.csv')
paired=pd.read_csv(R/'response_paired_tests.csv')
verify=pd.read_csv(R/'requirements_verification_status.csv')

doc=Document()
sec=doc.sections[0]; sec.top_margin=Inches(.7); sec.bottom_margin=Inches(.7); sec.left_margin=Inches(.75); sec.right_margin=Inches(.75)
styles=doc.styles
styles['Normal'].font.name='Arial'; styles['Normal'].font.size=Pt(10)
for sname in ['Heading 1','Heading 2','Heading 3']:
    styles[sname].font.name='Arial'
styles['Heading 1'].font.size=Pt(15); styles['Heading 2'].font.size=Pt(12)

t=doc.add_paragraph(); t.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=t.add_run('Executed Proof-of-Concept Report\nDigital Twin Assisted GNSS Spoofing Detection and Bounded Response'); r.bold=True; r.font.size=Pt(18)
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=p.add_run('Research execution record for the revised SDAV manuscript'); r.italic=True; r.font.size=Pt(11)

p=doc.add_paragraph()
r=p.add_run('Status statement. '); r.bold=True
p.add_run('A genuine PX4/Gazebo/ROS 2 software-in-the-loop experiment could not be executed in the present environment because ROS 2, Gazebo, Docker/Podman, and PX4 were not available, and the execution shell could not resolve GitHub to obtain the PX4 source. The experiment reported here is therefore an executed reduced-order 3D cyber-physical proof of concept. It implements the architecture logic but must not be described as PX4/Gazebo validation, hardware-in-the-loop validation, or flight validation.')

doc.add_heading('1. Purpose and evidential scope',level=1)
doc.add_paragraph('The purpose of this proof of concept was to test whether the principal information flows proposed in the manuscript can be implemented in an executable system: GNSS measurements are compared with a predictive digital twin and a GNSS-independent navigation source; the resulting residual evidence is interpreted by a probabilistic classifier; an assurance rule prevents stale digital-twin information from independently authorizing a response; and a bounded response can isolate GNSS and continue or terminate the mission using independent navigation. The experiment was designed as an architecture-level feasibility test rather than a realistic radio-frequency representation of GNSS spoofing.')
doc.add_paragraph('This scope is consistent with the literature showing that UAVs can be manipulated by deceptive GPS signals (Kerns et al., 2014), that spoofing defenses benefit from independent observables (Psiaki and Humphreys, 2016), and that independent inertial information can support spoofing detection (Vinoj and Lalu, 2024). The use of a model-based backup for recovery is also consistent with prior work demonstrating software-sensor recovery on robotic vehicles, including a quadrotor (Choi et al., 2020). These studies motivate the architecture but do not validate the numerical results of this simulator.')

doc.add_heading('2. Executed system',level=1)
doc.add_paragraph('The simulator uses a reduced-order three-dimensional translational vehicle model following a five-waypoint mission. Vehicle acceleration is generated by a bounded waypoint controller. The operational estimator is GNSS-dominant before detection and switches to a separate odometry surrogate after GNSS isolation. The digital twin propagates position and velocity using recent control inputs and is corrected by the independent odometry stream. Communication-delay scenarios delay these external twin inputs without altering the independent onboard navigation surrogate.')

add_table(doc,['Element','Executed implementation'],[
    ['Vehicle','3D translational waypoint-following surrogate; 20 Hz dynamics and control'],
    ['GNSS','5 Hz position and velocity observations with declared simulation noise'],
    ['Independent source','GNSS-independent odometry surrogate with measurement noise and random-walk bias'],
    ['Digital twin','Control-driven state propagation with independent-telemetry correction'],
    ['Evidence','Covariance-normalized twin residual, independent-navigation residual, and GNSS temporal residual'],
    ['Classifier','Standardized logistic regression using five multi-source features'],
    ['Assurance','Probability threshold + temporal persistence + stale-twin gate requiring independent evidence'],
    ['Response','Detection-only; fixed route-retracing return-to-base; or GNSS isolation with mission continuation'],
],font_size=8)

doc.add_heading('3. Experimental design',level=1)
doc.add_paragraph('Residual covariance matrices were estimated from a separate set of 25 nominal calibration trials. Detector thresholds were then established using a separate benign calibration set containing nominal operation, temporary GNSS degradation, and communication delay. Classifier training, validation, and held-out testing used disjoint random seeds so that individual simulation traces did not appear in more than one partition.')
add_table(doc,['Partition','Trials'],[
    ['Residual covariance calibration','25 nominal'],
    ['Benign threshold calibration','10 nominal + 10 GNSS degradation + 10 communication delay'],
    ['Classifier training','20 per scenario across six scenarios (120 total)'],
    ['Validation','8 per scenario (48 total)'],
    ['Held-out test','20 per scenario (120 total: 60 attack, 60 benign)'],
    ['Response-policy experiment','20 per scenario per policy (360 policy runs)'],
    ['Weak-attack stress test','30 per attack scenario (90 total)'],
],font_size=8)

doc.add_paragraph('The primary training/test attack family sampled abrupt horizontal position steps from 12 to 25 m with an additional 0 to 0.8 m/s velocity bias, or gradual horizontal carry-off rates from 0.25 to 0.80 m/s capped at 30 m. The combined spoofing-and-communication scenario additionally imposed 0.55 to 1.20 s of external-twin telemetry delay. These values are experimental simulator parameters, not claims about typical real-world spoofing magnitudes or aircraft tolerances.')
doc.add_paragraph('The weak-attack stress test intentionally moved outside the training range: abrupt position steps were reduced to 6â€“12 m, and gradual carry-off was reduced to 0.10â€“0.25 m/s. This additional test was included because performance on the same generative range used for training can overstate generalization.')

doc.add_heading('4. Detection methods',level=1)
doc.add_paragraph('Three detection configurations were compared. The GNSS-only temporal baseline used consistency between consecutive GNSS position/velocity observations. The twin-residual baseline used only the covariance-normalized disagreement between GNSS and the digital twin. The proposed detector combined the twin residual, the independent-navigation residual, the GNSS temporal residual, twin age, and GNSS route deviation in a logistic-regression classifier. A response alert required three consecutive positive samples. When the twin was stale, the alert additionally required strong independent-navigation evidence. Thresholds and persistence were selected using the validation data rather than the held-out test data.')
doc.add_paragraph(f'The final multi-source probability threshold was {info["probability_threshold"]:.3f}, with {info["persistence_samples"]} consecutive 5 Hz samples required for an event-level alert. On the held-out sample-level data, the probability output had a Brier score of {info["test_probability_calibration"]["brier_score"]:.3f}, a 10-bin expected calibration error of {info["test_probabity_calibration"]["ece_10_bins"]:.3f}, and an ROC AUC of {info["test_probability_calibration"]["roc_auc_probability"]:.3f}. These numbers describe calibration within this synthetic data-generating process and are not real-world AI assurance evidence.')

doc.add_heading('5. Held-out detection results',level=1)
rows=[]
for _,r in det.iterrows():
    rows.append([r.method,f'{int(r.attack_detected)}/{int(r.attack_trials)}',f'{r.recall:.3f} ({r.recall_ci95_low:.3f}â€“{r.recall_ci95_high:.3f})',f'{int(r.benign_false_alerts)}/{int(r.benign_trials)}',f'{r.false_alarm_rate:.3f} ({r.far_ci95_low:.3f}â€“{r.far_ci95_high:.3f})','' if pd.isna(r.median_latency_s) else f'{r.median_latency_s:.1f}'])
add_table(doc,['Method','Attacks detected','Recall (95% Wilson CI)','Benign false alerts','False-alert rate (95% Wilson CI)','Median latency (s)'],rows,font_size=7)
doc.add_paragraph('The GNSS-only temporal baseline did not detect any of the 60 held-out attack trials. This outcome is consistent with the design of the simulated attacks: both abrupt and gradual manipulations were constructed to preserve enough temporal coherence that consecutive GNSS observations alone were weak evidence. The twin-only detector detected 54 of 60 attack trials, but its median latency was 24.1 s and one benign communication-delay trial generated an event-level alert. The multi-source detector generated alerts in all 60 held-out attack trials and none of the 60 benign trials. The corresponding 95% Wilson interval for attack recall was 0.940â€“1.000 and for the false-alert rate was 0â€“0.060. The finite-sample intervals are important: the observed 100%/0% rates do not establish perfect population performance.')
doc.add_picture(str(F/'detection_performance.png'),width=Inches(6.1)); add_caption(doc,'Figure 1. Held-out trial-level detection performance in the reduced-order simulator.')

doc.add_heading('6. Scenario robustness and weak-attack stress test',level=1)
prop=scen[scen.method=='Multi-source + assurance']
rows=[]
for _,r in prop.iterrows():
    rows.append([r.scenario,f"{r.alert_rate:.3f}",'' if pd.isna(r.median_latency_s) else f"{r.median_latency_s:.1f}','' if pd.isna(r.p95_latency_s) else f'{r.p95_latency_s:.1f}'])
add_table(doc,['Held-out scenario','Alert rate','Median latency (s)','P95 latency (s)'],rows,font_size=8)
st=stress[stress.method=='Multi-source + assurance']
rows=[]
for _,r in st.iterrows():
    rows.append([r.scenario,f'{r.detection_rate:.3f},f'{r.median_latency_s:.1f}',f'{r.p95_latency_s:.1f}'])
add_table(doc,['Weak-attack scenario','Detection rate','Median latency (s)','P95 latency (s)'],rows,font_size=8)
doc.add_paragraph('The additional stress test shows that all 90 weaker attack trials were enduringly detected, but the latency penalty is substantial. The weak abrupt scenario has a median latency of 0.6 s, whereas weak gradual carry-off rises to 29.3 s and weak spoofing with communication delay rises to 32.2 s. The P95 latencies for the two weak gradual cases are 45.2 s and 48.6 s. This is an important qualification: eventual detection at lower magnitude does not imply that detection is sufficiently fast for a safety-critical vehicle.')
doc.add_picture(str(F/'stress_detection_rate.png'),width=Inches(5.8)); add_caption(doc,'Figure 2. Event-level detection rate for the multi-source detector under the weaker attack stress test.')

# Create probability plot from representative trace
tr=pd.read_csv(R/'representative_traces.csv'); tr=tr[tr.rep_scenario=='gradual_spoof']
import matplotlib.pyplot as plt
plt.figure(figsize=(8,4.8)); plt.plot(tr.time_s,tr.p_attack,label='Estimated attack probability'); plt.axhline(info['probability_threshold'],linestyle='--',label='Decision threshold'); plt.axvline(30,linestyle=':',label='Attack onset'); plt.xlabel('Time (s)'); plt.ylabel('Attack probability'); plt.ylim(-.02,1.02); plt.title('Representative gradual carry-off: probability and decision threshold'); plt.legend(); plt.tight_layout(); plt.savefig(F/'report_gradual_probability.png,dpi=220); plt.close()
doc.add_picture(str(F/'report_gradual_probability.png'),width=Inches(6.1)); add_caption(doc,'Figure 3. Representative gradual carry-off trace, showing classifier probability and the validation-selected decision threshold.')

doc.add_heading('7. Response-policy results',level=1)
doc.add_paragraph('Three policies were evaluated using the same scenario seeds: (1) detection only, in which GNSS remained active; (2) fixed return-to-base, in which GNSS was isolated and the vehicle retraced its previous route using the independent navigation source; and (3) bounded continuation, in which GNSS was isolated and the mission continued using the independent navigation source. The matched-seed design permits paired statistical comparison. The fixed return is intentionally not a single-waypoint homing command: the vehicle retraces the previously authorized route to reduce the need for a new path planner after GNSS is rejected.')
attack_resp=resp[resp.subset=='attack']
rows=[]
for _,r in attack_resp.iterrows():
    rows.append([r.strategy,f'{r.median_max_route_error_m:.2f}',f'{r.p95_max_route_error_m:.2f}',f'{r.boundary10_violation_rate:.3f}',f'{r.boundary20_violation_rate:.3f}',f'{r.mission_completion_rate:.3f}',f'{r.return_home_rate:.3f}'])
add_table(doc,['Policy','Median max deviation (m)','P95 max deviation (m)','>10 m rate','>20 m rate','Mission completion','Return home'],rows,font_size=7.3)

doc.add_paragraph('Across 60 paired attack trials, the median maximum true route deviation was 17.39 m with detection only, 2.89 m with the fixed return-to-base policy, and 2.63 m with bounded continuation. A paired Wilcoxon signed-rank comparison between detection-only and bounded continuation gave p < 0.001. The fixed and bounded policies also differed statistically (p = 0.00013), but their median paired difference was only 0.20 m; this small effect should not be presented as a practically important safety advantage without a mission-specific safety model. The 10 m and 20 m boundaries used in this analysis are diagnostic thresholds only and are not regulatory or certified safety limits.')
doc.add_paragraph('The bounded policy completed all 60 attack missions in the simulator after switching to the independent navigation source. The fixed policy intentionally terminated the mission objective and returned to the launch point in 36 of 60 attack trials before the 90 s simulation ended. The remaining fixed-policy trials were still executing the return trajectory when the simulation terminated. These outcomes mainly illustrate the trade-off between mission continuation and conservative termination; they do not establish which policy would be preferable in an actual aircraft.')
doc.add_picture(str(F/'response_route_deviation.png'),width=Inches(6.1)); add_caption(doc,'Figure 4. Maximum true route deviation under the three response policies for the paired attack trials.')

doc.add_heading('8. Requirements exercised by the proof of concept',level=1)
doc.add_paragraph('The experiment does not verify every requirement proposed in Section 5. The table below summarizes the evidential status. This distinction should be preserved in the manuscript and reviewer response.')
rows=[]
for _,r in verify.iterrows(): rows.append([r.requirement_id,r.status_in_executed_poc,r.evidence,r.important_limit])
add_table(doc,['Req.','Status','Evidence in this execution','Limit'],rows,font_size=6.8)

doc.add_heading('9. Interpretation and publication limits',level=1)
doc.add_paragraph('The executed proof of concept provides evidence that the architecture can be made computationally explicit in a reduced-order simulation and that multi-source evidence can outperform two intentionally simpler residual baselines within the defined synthetic scenario family. It also demonstrates the functional difference between detection, source isolation, and response policy. These are useful architecture-level results, but they are not sufficient to claim operational cyber resilience.')
for text in [
    'The flight dynamics are reduced-order translational dynamics rather than PX4 flight-control dynamics.',
    'GNSS spoofing is represented as controlled position/velocity bias. Carrier tracking, correlation peaks, signal power, Doppler, multipath physics, receiver acquisition, and RF propagation are not simulated.',
    'The independent navigation source is a synthetic odometry surrogate, not a real INS, visual-inertial estimator, or certified navigation source.',
    'Training, validation, and main held-out test data are generated by the same simulator family, although disjoint random seeds and an out-of-range weak-attack stress test were used.',
    'The AI assurance implementation is partial. Probability calibration and a stale-twin gate were evaluated; explicit out-of-distribution detection, explanation consistency, provenance enforcement, and adversarial ML testing were not implemented.',
    'Cryptographic telemetry protection, replay defense, tamper-evident audit storage, human operator timing, GNSS reintegration, and software/configuration signing were not executed.',
    'The response-policy comparison uses simplified mission logic. The route-deviation thresholds are analytical values and are not aviation safety standards.',
]: add_bullet(doc,text)

doc.add_paragraph('Accordingly, a defensible manuscript description would be: â€œA reduced-order software proof of concept was executed to test the internal information-flow and response logic of the proposed architecture.â€ It would not be defensible to write that the architecture has been validated in PX4/Gazebo, that it has been proven cyber-resilient, or that the results establish airworthiness or certification readiness.')

doc.add_heading('10. Required next validation stage',level=1)
doc.add_paragraph('The next stage should migrate the same test logic into a genuine PX4/Gazebo software-in-the-loop environment. PX4 is an open-source autopilot supporting SITLH[™“ÔÈ‹ÑÈ[YÜ˜][Ûˆ[™›ÝšY\ÈÚ[][]Üˆ˜Z[\™KZ[š™XÝ[ÛˆYXÚ[š\Û\ÎÈÝÙ]™\‹]ÈÙ[™\šXÈ8 'Ü›Û™ÈÔø 'H˜Z[\™H[ÙH\È›ÝHÝXœÝ]]H›ÜˆHÛÛ›ÛYÜ˜YX[Ø\œžK[Ù™ˆÜÛÙš[™È[Ù[ˆH™^^\š[Y[ÚÝ[\™Y›Ü™H[š™XÝ™\›ÙXÚX›HÓ”ÔÈÜÚ][Û‹Ý™[ØÚ]HšX\È]HÚ[][]ÜˆÜˆÙ[œÛÜ‹[Y\ÜØYÙH›Ý[™\žK™]Z[ˆÚ[][]ÜˆÜ›Ý[™]Û›H›Üˆ]˜[X][Û‹[™™XÛÜ™\Ý[X]Üˆ[››Ý˜][ÛœË™ZXÛHÝ]KÛÛ[][šXØ][Ûˆ[Z[™Ë]XÝÜˆÝ]][™™\ÜÛœÙHÛÛ[X[™ËˆH^\š[Y[[˜\šXX›\È[™Y]šXÜÈ[™XYHYš[™Y[ˆÙXÝ[ÛˆÈØ[ˆ™H™]\ÙY‰ÊB‚™ØË˜YÚXY[™Ê	Ô™Y™\™[˜Ù\ÉË]™[LJBœ™YœÏVÂ‰ÐÚÚK‹Ø]KË‹XY™\‹K‹š[™Ë‹[™Kˆ
ŒŒ
KˆÛÙØ\™KX˜\ÙY™X[[YH™XÛÝ™\žHœ›ÛHÙ[œÛÜˆ]XÚÜÈÛˆ›Ø›ÝXÈ™ZXÛ\Ëˆ›ØÙYY[™ÜÈÙˆHŒÜ™[\›˜][Û˜[Þ[\ÜÚ][HÛˆ™\ÙX\˜Ú[ˆ]XÚÜË[\Ú[ÛœÈ[™Y™[œÙ\È
RQŒŒ
KÍKLÍ‰Ë‰ÒÙ\›œËKˆ‹‹Ú\\™ˆ‹š]K‹ˆK‹[™[\™^\ËˆKˆ
ŒM
Kˆ[›X[›™YZ\˜Ü˜YØ\\™H[™ÛÛ›ÛšXHÔÈÜÛÙš[™Ëˆ›Ý\›˜[ÙˆšY[›Ø›ÝXÜËÌJ
KŒMËMŒÍ‹ˆÎ‹ËÙÚK›Ü™ËÌLŒL‹Ü›Ø‹ŒŒMLLË‰Ë‰ÓYZY\‹‹[™HÛÛšX]ÜœËˆ]]Ü[Ýˆ™[›ÙËˆÎ‹ËÙÚK›Ü™ËÌLLŽKÞ™[›ÙËNMMÌ‹‰Ë‰Ô\ØÚ[KˆË‹[™Û]\ËˆKˆ
Œ
KˆÝØ\™È˜][X[˜YÙ[Y[]]Û›Û^HHH]™[ÜY[[™]˜[X][ÛˆÙˆHÙ[‹TÝY™šXÚY[[›ÛX[H™\ÜÛœÙHÞ\Ý[H\˜Ú]XÝ\™H›ÜˆY\ÜXÙHXš]]ËˆLÜ™[\›˜][Û˜[ÛÛ™™\™[˜ÙHÛˆ[š\›Û›Y[[Þ\Ý[\ËPÑTËLŒMŒ‰Ë‰ÔÚXZÚKKˆ‹[™[\™^\ËˆKˆ
ŒMŠKˆÓ”ÔÈÜÛÙš[™È[™]XÝ[Û‹ˆ›ØÙYY[™ÜÈÙˆHQQQKL
ŠKLNLLÌˆÎ‹ËÙÚK›Ü™ËÌLŒLLKÒ”“ÐËŒŒM‹ŒLN‰Ë‰ÕX˜\ÜÚKKˆ
ŒŒÊKˆ\YšXÚX[[[YÙ[˜ÙHš\ÚÈX[˜YÙ[Y[œ˜[Y]ÛÜšÈ
RH“QˆKŒ
Kˆ’TÕRHLLKˆÎ‹ËÙÚK›Ü™ËÌLŒŽÓ’TÕRKŒLLK‰Ë‰Õš[›Ú‹‹ˆË‹[™[K‹ˆ
Œ
KˆS”ÈZYYÜÛÙš[™È]XÝ[ÛˆÙˆYÚ[˜[ZXÈÓ”ÔÈ™XÙZ]™\ˆ›Üˆ][˜Ú™ZXÛH\XØ][ÛœÎˆHÛÜÙ[HÛÝ\Y\›ØXÚˆY˜[˜Ù\È[ˆÜXÙH™\ÙX\˜ÚÍ
ŠKŽMLŽŽKˆÎ‹ËÙÚK›Ü™ËÌLŒLM‹Ú‹˜\Ü‹ŒŒŒËŒN‰Ë‰ÕÙZK‹Ý[‹Ë‹K‹[™XK‹ˆ
Œ
KˆÓ”ÔÈÜÛÙš[™È]XÝ[Ûˆ›ÜˆPUœÈ\Ú[™ÈÜ\ˆœ™\]Y[˜ÞH[™Ø\œšY\‹]ËS›Ú\ÙH[œÚ]H˜][Ëˆ›Ý\›˜[ÙˆÞ\Ý[\È\˜Ú]XÝ\™KMLËLÌŒL‹ˆÎ‹ËÙÚK›Ü™ËÌLŒLM‹Ú‹œÞ\Ø\˜ËŒŒŒLÌŒL‹‰Ë—B™›Üˆ™Yˆ[ˆ™YœÎ‚ˆYØË˜YÜ\˜YÜ˜\
™YŠNÈœ\˜YÜ˜\Ù›Ü›X]™š\œÝÛ[™WÚ[™[R[˜Ú\ÊKŒŠNÈœ\˜YÜ˜\Ù›Ü›X]›YÚ[™[R[˜Ú\ÊŒŠNÈœ\˜YÜ˜\Ù›Ü›X]œÜXÙWØY\T

B‚™ØËœØ]™JÕU
Bœš[
ÕU
B