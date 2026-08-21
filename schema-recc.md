        system_prompt = """You are an expert clinical physiotherapist and diagnostician specializing in musculoskeletal conditions.

You use the "Provisional Diagnosis AI View" framework. You MUST respond with a single valid JSON object — no markdown, no prose, no code fences.

PROBABILITY TIER SYSTEM (1-5):
- Tier 5 — Very Likely: Multi-layer convergence (history + objective + biomechanics all align, no competing Tier 4 drivers)
- Tier 4 — Likely: Strong positives but meaningful alternative explanations exist
- Tier 3 — Plausible: Fits the data but not dominant
- Tier 2 — Unlikely: Some fit but current dataset doesn't support it
- Tier 1 — Very Unlikely: Rule-out only

RULES:
- Differentials must be DECISION-CHANGING: only include if confirming it would materially change rehab direction, constraints, or referral pathway — NOT just because it's plausible
- A differential MUST have a tier >= the provisional diagnosis tier — if it's less likely than the primary, it cannot displace it and should NOT be listed
- If the provisional is Tier 5, there are no valid differentials — return an empty array
- Prefer 1-3 high-quality differentials over a long list of plausible ones
- Do NOT include differentials that would result in the same rehab program as the provisional diagnosis
- Sufficiency gate must be honest — don't force convergence if drivers overlap
- Tier assignment must reflect actual data convergence, not optimism
- VALD analysis must address absolute values, not just asymmetry
- Low absolute force = global weakness; asymmetric force = unilateral deficit

Respond with this exact JSON structure:
{
  "intake_snapshot": "string — condensed complaint summary with context and irritability flags",
  "provisional_diagnosis": "string — specific diagnosis label (not 'Unknown')",
  "diagnostic_bucket": {
    "primary_bucket": "string",
    "secondary_bucket": "string or null",
    "bucket_reasoning": "string"
  },
  "probability_tier": {
    "tier": 1-5,
    "label": "Very Unlikely|Unlikely|Plausible|Likely|Very Likely",
    "rationale": "string — why this tier, what evidence supports/against"
  },
  "why_not_higher_tier": "string or null — what prevents higher confidence",
  "biomechanical_summary": "string — what VALD supports and rules out",
  "vald_supports_diagnosis": true/false,
  "biomechanical_deficits": ["string"],
  "diagnostic_sufficiency": {
    "is_sufficient": true/false,
    "sufficiency_answer": "string",
    "driver_systems": [{"driver": "string", "evidence_present": "Yes/No/Partial", "rehab_direction_impact": "string"}],
    "why_not_sufficient": "string or null"
  },
  "differential_diagnoses": [
    {
      "diagnosis": "string",
      "tier": 1-5,
      "tier_label": "string",
      "fits_because": ["string"],
      "directional_impact": "string — how rehab changes if confirmed",
      "included_reason": "string — what decision this changes"
    }
  ],
  "decision_changing_missing_data": [
    {
      "category": "string",
      "missing_tests": ["string"],
      "impact_if_positive": "string"
    }
  ],
  "risk_factors": ["string"],
  "protective_factors": ["string"],
  "expected_recovery_timeline": "string",
  "return_to_activity_probability": "string",
  "recommended_interventions": ["string"],
  "contraindicated_activities": ["string"],
  "red_flags": ["string"],
  "monitoring_parameters": ["string"],
  "reassessment_timeline": "string",
  "positioning_summary": {
    "provisional_bucket": "string",
    "probability": "string",
    "sufficiency": "string",
    "competing_drivers": "string",
    "additional_data_required": "string"
  }
}"""

        user_prompt = f"""Analyze this patient using the Provisional Diagnosis AI View framework.

CLINICAL FINDINGS:
- Chief Complaint: {clinical_findings.chief_complaint}
- Clinical History: {clinical_findings.clinical_history}
- Duration: {clinical_findings.duration_months} months (Stage: {clinical_findings.clinical_stage})
- Primary Joint: {clinical_findings.primary_joint}
- Functional Region: {clinical_findings.functional_region}
- Subjective Notes: {clinical_findings.subjective_notes}

VALD BIOMECHANICAL DATA:
- Strength Asymmetry: {vald_data.strength_asymmetry_percent}%
- ROM Asymmetry: {vald_data.rom_asymmetry_degrees}°
- Absolute Force Level: {vald_data.absolute_force_level or 'Not available'}
- Peak Force: {vald_data.peak_force_newtons}N
- Bilateral Force Ratio: {vald_data.bilateral_force_ratio}
- Compensation Patterns: {', '.join(vald_data.compensation_patterns) if vald_data.compensation_patterns else 'None identified'}

FORCE PRODUCTION ANALYSIS:
{force_analysis}

CLINICIAN'S PROVISIONAL DIAGNOSIS: {existing_diagnosis or 'Not provided'}

VALD FIRST-SESSION EXERCISE DATA:
{self._format_vald_exercises(patient_data.get('vald_exercises', {}))}

Return ONLY the JSON object. No markdown, no explanation outside the JSON."""

        ai_text = ""
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            response = self.llm.invoke(messages)
            ai_text = response.content.strip()

            # Use robust cleaning for JSON response
            json_str = clean_json_response(ai_text)
            ai_json = json.loads(json_str)
            return self._build_analysis_from_json(ai_json, vald_data, clinical_findings, evidence_findings)

        except json.JSONDecodeError as e:
            print(f"⚠️  JSON parse failed: {e}")
            # Try to salvage truncated JSON by finding the last complete top-level field
            try:
                # Find the last complete '}' that closes the root object
                last_brace = ai_text.rfind('\n}')
                if last_brace > 0:
                    truncated = ai_text[:last_brace + 2]
                    ai_json = json.loads(truncated)
                    print("   ✅ Recovered from truncated JSON")
                    return self._build_analysis_from_json(ai_json, vald_data, clinical_findings, evidence_findings)
            except Exception:
                pass
            print(f"   AI response (first 500 chars): {ai_text[:500]}")
            return self._create_enhanced_fallback_analysis(
                vald_data, clinical_findings, evidence_findings, existing_diagnosis
            )
        except Exception as e:
            import traceback
            print(f"❌ Error in prognosis analysis: {e}")
            traceback.print_exc()
            return self._create_enhanced_fallback_analysis(
                vald_data, clinical_findings, evidence_findings, existing_diagnosis
            )

    def _build_analysis_from_json(self, data: Dict[str, Any], vald_data: VALDAssessment,
                                   clinical_findings: ClinicalFindings,
                                   evidence_findings: EvidenceBasedFindings) -> PrognosisAnalysis:
        """Build PrognosisAnalysis directly from the AI's JSON response."""

        tier_labels = {1: "Very Unlikely", 2: "Unlikely", 3: "Plausible", 4: "Likely", 5: "Very Likely"}

        # ── Probability tier ──────────────────────────────────────────────────
        pt = data.get("probability_tier", {})
        tier_num = int(pt.get("tier", 3))
        probability_tier = ProbabilityTier(
            tier=tier_num,
            label=pt.get("label", tier_labels.get(tier_num, "Plausible")),
            rationale=pt.get("rationale", "")
        )

        # ── Diagnostic bucket ─────────────────────────────────────────────────
        db = data.get("diagnostic_bucket", {})
        diagnostic_bucket = DiagnosticBucket(
            primary_bucket=db.get("primary_bucket", clinical_findings.primary_joint or "Musculoskeletal"),
            secondary_bucket=db.get("secondary_bucket"),
            bucket_reasoning=db.get("bucket_reasoning", "")
        )

        # ── Diagnostic sufficiency ────────────────────────────────────────────
        ds = data.get("diagnostic_sufficiency", {})
        diagnostic_sufficiency = DiagnosticSufficiency(
            is_sufficient=bool(ds.get("is_sufficient", False)),
            sufficiency_answer=ds.get("sufficiency_answer", ""),
            driver_systems=ds.get("driver_systems", []),
            why_not_sufficient=ds.get("why_not_sufficient")
        )

        # ── Differentials ─────────────────────────────────────────────────────
        provisional_tier = probability_tier.tier
        differentials = []
        for d in data.get("differential_diagnoses", []):
            t = int(d.get("tier", 3))
            # Only include differentials that are at or above the provisional tier
            # — a lower-tier differential cannot displace the primary diagnosis
            if t < provisional_tier:
                continue
            differentials.append(DifferentialDiagnosis(
                diagnosis=d.get("diagnosis", ""),
                tier=t,
                tier_label=d.get("tier_label", tier_labels.get(t, "Plausible")),
                fits_because=d.get("fits_because", []),
                directional_impact=d.get("directional_impact", ""),
                included_reason=d.get("included_reason", "")
            ))

        # ── Missing data ──────────────────────────────────────────────────────
        missing_data = []
        for m in data.get("decision_changing_missing_data", []):
            missing_data.append(DecisionChangingMissingData(
                category=m.get("category", ""),
                missing_tests=m.get("missing_tests", []),
                impact_if_positive=m.get("impact_if_positive", "")
            ))

        return PrognosisAnalysis(
            intake_snapshot=data.get("intake_snapshot", ""),
            biomechanical_summary=data.get("biomechanical_summary", self._interpret_comprehensive_vald_findings(vald_data)),
            force_production_analysis=data.get("force_production_analysis", self._analyze_force_production_comprehensively(vald_data, clinical_findings)),
            biomechanical_deficits=data.get("biomechanical_deficits", []),
            vald_supports_diagnosis=bool(data.get("vald_supports_diagnosis", False)),
            provisional_diagnosis=data.get("provisional_diagnosis", clinical_findings.chief_complaint or "Unknown"),
            diagnostic_bucket=diagnostic_bucket,
            probability_tier=probability_tier,
            why_not_higher_tier=data.get("why_not_higher_tier"),
            diagnostic_sufficiency=diagnostic_sufficiency,
            differential_diagnoses=differentials,
            decision_changing_missing_data=missing_data,
            research_evidence=evidence_findings,
            risk_factors=data.get("risk_factors", []),
            protective_factors=data.get("protective_factors", []),
            expected_recovery_timeline=data.get("expected_recovery_timeline", ""),
            return_to_activity_probability=data.get("return_to_activity_probability", ""),
            recommended_interventions=data.get("recommended_interventions", []),
            contraindicated_activities=data.get("contraindicated_activities", []),
            red_flags=data.get("red_flags", []),
            follow_up_vald_recommended=True,
            monitoring_parameters=data.get("monitoring_parameters", []),
            reassessment_timeline=data.get("reassessment_timeline", "6-8 weeks"),
            positioning_summary=data.get("positioning_summary", {})
        )

    def _infer_probability_tier(self, vald_data: VALDAssessment, clinical_findings: ClinicalFindings, existing_diagnosis: str) -> int:
        """Infer probability tier based on data convergence."""
        score = 0
        if existing_diagnosis:
            score += 2
        if vald_data.absolute_force_level:
            score += 1
        if vald_data.strength_asymmetry_percent is not None:
            score += 1
        if clinical_findings.chief_complaint and len(clinical_findings.chief_complaint) > 20:
            score += 1
        if clinical_findings.duration_months:
            score += 1
        # Multi-region or complex presentation reduces tier
        if clinical_findings.functional_region and "multi" in clinical_findings.functional_region.lower():
            score -= 1
        return max(1, min(5, score))

    def _generate_tiered_differentials(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[DifferentialDiagnosis]:
        """Generate decision-changing differential diagnoses with tiers."""
        differentials = []
        region = (clinical_findings.functional_region or "").lower()
        joint = (clinical_findings.primary_joint or "").lower()
        duration = clinical_findings.duration_months or 0
        
        # Neurodynamic sensitivity — relevant for spine/upper limb
        if any(k in region for k in ["spine", "upper", "cervical"]):
            differentials.append(DifferentialDiagnosis(
                diagnosis="Neurodynamic mechanosensitivity / cervicothoracic contribution",
                tier=4, tier_label="Likely",
                fits_because=["Neural tension signs possible with upper limb/spine involvement", "Trapezius tightness may be protective"],
                directional_impact="Requires neural load pacing, end-range dosing, irritability staging — changes loading constraints significantly",
                included_reason="Would shift emphasis away from local structural rehab toward neural irritability management"
            ))
        
        # Global load tolerance — relevant for chronic/multi-region
        if duration > 3:
            differentials.append(DifferentialDiagnosis(
                diagnosis="Global load tolerance / movement capacity deficit",
                tier=4, tier_label="Likely",
                fits_because=["Chronic duration", "VALD shows " + (vald_data.absolute_force_level or "unknown") + " absolute force"],
                directional_impact="Emphasises capacity restoration and progressive systemic loading over local joint rehab",
                included_reason="Changes rehab from local to systemic — fundamentally different programming"
            ))
        
        # Rotator cuff / shoulder specific
        if "shoulder" in joint:
            differentials.append(DifferentialDiagnosis(
                diagnosis="Subacromial bursitis vs rotator cuff tendinopathy",
                tier=4, tier_label="Likely",
                fits_because=["Overhead pain pattern", "Load-dependent irritability"],
                directional_impact="Bursitis = slower loading progression; tendinopathy = earlier progressive loading",
                included_reason="Changes loading speed and compression tolerance in early rehab"
            ))
        
        # Lumbar referral — relevant for lower limb / posterior chain
        if any(k in region for k in ["lower", "posterior", "lumbar"]):
            differentials.append(DifferentialDiagnosis(
                diagnosis="Lumbar referral / radicular contribution",
                tier=3, tier_label="Plausible",
                fits_because=["Lower limb symptoms", "Posterior chain involvement"],
                directional_impact="Adds neuro screen, irritability framework, avoids provocative flexion loading",
                included_reason="Would change loading choices and add neural precautions"
            ))
        
        return differentials

    def _identify_decision_changing_missing_data(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[DecisionChangingMissingData]:
        """Identify only missing data that could re-rank differentials or change direction."""
        missing = []
        region = (clinical_findings.functional_region or "").lower()
        
        if any(k in region for k in ["spine", "upper", "cervical"]):
            missing.append(DecisionChangingMissingData(
                category="Separate neurodynamic vs structural driver",
                missing_tests=["Myotomes / dermatomes / reflexes", "Symptom change with cervical repositioning", "Neural loading tolerance staging"],
                impact_if_positive="Neurodynamic contribution moves to Tier 5 — changes loading constraints and dosing"
            ))
        
        if not vald_data.strength_asymmetry_percent:
            missing.append(DecisionChangingMissingData(
                category="Quantify bilateral force deficit",
                missing_tests=["ForceFrame isometric testing", "ForceDeck jump/landing assessment"],
                impact_if_positive="Could confirm or rule out unilateral deficit vs global weakness — changes rehab target"
            ))
        
        missing.append(DecisionChangingMissingData(
            category="Confirm primary vs secondary driver",
            missing_tests=["Single-leg squat / step-down quality", "Scapular assistance observation (if shoulder)", "Repeated movement response"],
            impact_if_positive="Identifies whether local control or systemic capacity is the primary driver"
        ))
        
        return missing

    def _interpret_comprehensive_vald_findings(self, vald_data: VALDAssessment) -> str:
        """Comprehensive interpretation of all VALD assessment findings."""
        
        findings = []
        
        # Absolute force analysis (primary focus)
        if vald_data.absolute_force_level:
            if vald_data.absolute_force_level == "Low":
                findings.append("CRITICAL: Low absolute force production indicates significant global weakness requiring immediate strength intervention")
            elif vald_data.absolute_force_level == "Medium":
                findings.append("Moderate absolute force production - adequate for daily activities but may limit higher-level function")
            else:
                findings.append("Good absolute force production capacity - strength adequate for most functional demands")
        
        # Asymmetry in context of absolute values
        if vald_data.strength_asymmetry_percent is not None:
            asymmetry = vald_data.strength_asymmetry_percent
            if vald_data.absolute_force_level == "Low" and asymmetry > 15:
                findings.append(f"Combined low absolute force ({vald_data.absolute_force_level}) with significant asymmetry ({asymmetry:.1f}%) indicates complex bilateral deficit")
            elif asymmetry > 20:
                findings.append(f"Significant strength asymmetry ({asymmetry:.1f}%) requiring targeted unilateral strengthening")
            elif asymmetry > 15:
                findings.append(f"Moderate strength asymmetry ({asymmetry:.1f}%) - monitor and address if functional limitations present")
            else:
                findings.append(f"Acceptable strength asymmetry ({asymmetry:.1f}%) - within normal functional range")
        
        # Normative data comparison
        if vald_data.age_matched_percentile:
            percentile = vald_data.age_matched_percentile
            if percentile < 25:
                findings.append(f"Below average performance ({percentile}th percentile) compared to age-matched peers")
            elif percentile > 75:
                findings.append(f"Above average performance ({percentile}th percentile) compared to age-matched peers")
            else:
                findings.append(f"Average performance ({percentile}th percentile) compared to age-matched peers")
        
        # Movement quality assessment
        if vald_data.movement_variability is not None:
            variability = vald_data.movement_variability
            if variability > 0.15:
                findings.append(f"High movement variability ({variability:.2f}) indicates poor motor control requiring neuromuscular re-education")
            elif variability < 0.10:
                findings.append(f"Excellent movement consistency ({variability:.2f}) indicating good motor control")
            else:
                findings.append(f"Moderate movement variability ({variability:.2f}) - acceptable but could be optimized")
        
        # Compensation patterns
        if vald_data.compensation_patterns:
            patterns = ", ".join(vald_data.compensation_patterns)
            findings.append(f"Movement compensations identified: {patterns} - require specific corrective interventions")
        
        # First assessment significance
        if vald_data.is_first_assessment:
            findings.append("First VALD assessment establishes critical baseline for monitoring treatment progress and return-to-activity decisions")
        
        return "; ".join(findings) if findings else "Limited VALD data available for comprehensive analysis"

    def _identify_comprehensive_risk_factors(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Identify comprehensive risk factors based on evidence and VALD data."""
        
        risk_factors = []
        
        # Clinical risk factors
        if clinical_findings.clinical_stage == "chronic":
            risk_factors.append("Chronic pain condition (>12 weeks) - associated with central sensitization risk")
        
        if clinical_findings.duration_months and clinical_findings.duration_months > 12:
            risk_factors.append("Extended symptom duration (>12 months) - associated with poorer outcomes")
        
        # VALD-based risk factors (comprehensive analysis)
        if vald_data.absolute_force_level == "Low":
            risk_factors.append("Low absolute force production - primary risk factor for delayed recovery and re-injury")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 20:
            risk_factors.append(f"Significant strength asymmetry ({vald_data.strength_asymmetry_percent:.1f}%) - associated with increased re-injury risk")
        
        if vald_data.movement_variability and vald_data.movement_variability > 0.15:
            risk_factors.append("Poor movement control - associated with compensatory movement patterns")
        
        if vald_data.age_matched_percentile and vald_data.age_matched_percentile < 25:
            risk_factors.append("Below-average physical capacity compared to peers - may limit recovery potential")
        
        # Compensation pattern risks
        if vald_data.compensation_patterns:
            risk_factors.append("Movement compensation patterns present - risk of secondary injury development")
        
        return risk_factors

    def _identify_protective_factors(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Identify protective factors that support positive prognosis."""
        
        protective_factors = []
        
        # VALD-based protective factors
        if vald_data.absolute_force_level in ["Medium", "High"]:
            protective_factors.append("Adequate absolute force production - supports functional recovery")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent < 10:
            protective_factors.append("Minimal strength asymmetry - indicates good bilateral function")
        
        if vald_data.movement_variability and vald_data.movement_variability < 0.10:
            protective_factors.append("Excellent movement control - supports stable recovery")
        
        if vald_data.age_matched_percentile and vald_data.age_matched_percentile > 75:
            protective_factors.append("Above-average physical capacity - supports optimal recovery potential")
        
        # Clinical protective factors
        if clinical_findings.clinical_stage in ["acute", "subacute"]:
            protective_factors.append("Early-stage condition - better prognosis for full recovery")
        
        if not vald_data.compensation_patterns:
            protective_factors.append("No significant movement compensations identified")
        
        return protective_factors

    def _calculate_evidence_based_prognosis(self, clinical_findings: ClinicalFindings, 
                                          vald_data: VALDAssessment, 
                                          evidence_findings: EvidenceBasedFindings) -> tuple[str, str]:
        """Calculate evidence-based recovery timeline and return-to-activity probability."""
        
        # Base timeline from clinical stage
        base_timelines = {
            "acute": 4,      # 4 weeks
            "subacute": 8,   # 8 weeks
            "chronic": 16    # 16 weeks
        }
        
        base_weeks = base_timelines.get(clinical_findings.clinical_stage, 12)
        
        # Modify based on VALD findings
        modifier = 1.0
        
        if vald_data.absolute_force_level == "Low":
            modifier *= 1.5  # 50% longer for low force production
        elif vald_data.absolute_force_level == "High":
            modifier *= 0.8  # 20% shorter for high force production
        
        if vald_data.strength_asymmetry_percent:
            if vald_data.strength_asymmetry_percent > 25:
                modifier *= 1.4
            elif vald_data.strength_asymmetry_percent < 10:
                modifier *= 0.9
        
        if vald_data.movement_variability:
            if vald_data.movement_variability > 0.15:
                modifier *= 1.2
            elif vald_data.movement_variability < 0.10:
                modifier *= 0.9
        
        final_weeks = int(base_weeks * modifier)
        
        # Format timeline
        if final_weeks <= 4:
            timeline = f"{final_weeks} weeks"
        elif final_weeks <= 12:
            timeline = f"{final_weeks//4}-{(final_weeks//4)+1} months"
        else:
            timeline = f"{final_weeks//4}-{(final_weeks//4)+2} months"
        
        # Calculate return-to-activity probability
        probability_score = 80  # Base probability
        
        # Adjust based on factors
        if vald_data.absolute_force_level == "Low":
            probability_score -= 20
        elif vald_data.absolute_force_level == "High":
            probability_score += 10
        
        if vald_data.strength_asymmetry_percent:
            if vald_data.strength_asymmetry_percent > 20:
                probability_score -= 15
            elif vald_data.strength_asymmetry_percent < 10:
                probability_score += 10
        
        if clinical_findings.clinical_stage == "chronic":
            probability_score -= 15
        elif clinical_findings.clinical_stage == "acute":
            probability_score += 10
        
        probability_score = max(30, min(95, probability_score))  # Clamp between 30-95%
        
        return timeline, f"{probability_score}% probability of successful return to pre-injury activity level"

    def _generate_evidence_based_interventions(self, clinical_findings: ClinicalFindings, 
                                             vald_data: VALDAssessment, 
                                             evidence_findings: EvidenceBasedFindings) -> List[str]:
        """Generate evidence-based interventions targeting specific deficits."""
        
        interventions = []
        
        # Force production-specific interventions
        if vald_data.absolute_force_level == "Low":
            interventions.append("Progressive resistance training focusing on absolute force development")
            interventions.append("Compound movement patterns to address global strength deficits")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 15:
            interventions.append("Unilateral strength training to address bilateral imbalances")
            interventions.append("Functional movement retraining with emphasis on symmetrical loading")
        
        # Movement quality interventions
        if vald_data.movement_variability and vald_data.movement_variability > 0.15:
            interventions.append("Motor control exercises to improve movement consistency")
            interventions.append("Proprioceptive training and neuromuscular re-education")
        
        # Compensation pattern-specific interventions
        if vald_data.compensation_patterns:
            interventions.append("Movement pattern correction targeting identified compensations")
            interventions.append("Mobility work for restricted movement patterns")
        
        # Stage-specific interventions
        if clinical_findings.clinical_stage == "chronic":
            interventions.append("Pain science education and graded exposure therapy")
            interventions.append("Cognitive-behavioral approaches for chronic pain management")
        
        # Evidence-based additions
        interventions.append("Manual therapy for short-term pain relief and mobility improvement")
        interventions.append("Regular VALD reassessment to monitor objective progress")
        
        return interventions

    def _identify_contraindicated_activities(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Identify activities to avoid during recovery based on deficits."""
        
        contraindications = []
        
        if vald_data.absolute_force_level == "Low":
            contraindications.append("High-load activities until strength improves to Medium level")
            contraindications.append("Explosive/ballistic movements until force production adequate")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 20:
            contraindications.append("Unilateral loading activities that may worsen asymmetry")
            contraindications.append("Sport-specific activities until asymmetry <15%")
        
        if vald_data.movement_variability and vald_data.movement_variability > 0.15:
            contraindications.append("Complex movement patterns until motor control improves")
            contraindications.append("Fatiguing activities that may worsen movement quality")
        
        if clinical_findings.clinical_stage == "acute":
            contraindications.append("Aggressive stretching or mobilization during inflammatory phase")
        
        return contraindications

    def _generate_comprehensive_monitoring_parameters(self, vald_data: VALDAssessment) -> List[str]:
        """Generate comprehensive parameters to monitor during treatment."""
        
        parameters = ["Pain levels (NPRS 0-10)", "Functional capacity and activity tolerance"]
        
        # VALD-specific monitoring
        if vald_data.absolute_force_level:
            parameters.append("Absolute force production progression")
        
        if vald_data.strength_asymmetry_percent is not None:
            parameters.append("Bilateral strength asymmetry reduction")
        
        if vald_data.movement_variability is not None:
            parameters.append("Movement consistency and quality")
        
        if vald_data.compensation_patterns:
            parameters.append("Resolution of movement compensation patterns")
        
        # Functional monitoring
        parameters.extend([
            "Return-to-activity milestones",
            "Patient-reported outcome measures",
            "Objective functional testing results"
        ])
        
        return parameters

    def _determine_reassessment_timeline(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> str:
        """Determine appropriate reassessment timeline based on condition and deficits."""
        
        if clinical_findings.clinical_stage == "acute":
            return "2-3 weeks (post-inflammatory phase)"
        elif vald_data.absolute_force_level == "Low":
            return "4-6 weeks (allow time for strength gains)"
        elif vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 20:
            return "4-6 weeks (monitor asymmetry correction)"
        else:
            return "6-8 weeks (standard reassessment interval)"

    def _extract_comprehensive_indicators(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Extract comprehensive clinical indicators."""
        
        indicators = []
        
        # Primary VALD indicators
        if vald_data.absolute_force_level == "Low":
            indicators.append("Low absolute force production (primary concern)")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 15:
            indicators.append("Significant bilateral strength imbalance")
        
        if vald_data.movement_variability and vald_data.movement_variability > 0.15:
            indicators.append("Poor motor control and movement consistency")
        
        # Clinical indicators
        if clinical_findings.duration_months and clinical_findings.duration_months > 12:
            indicators.append("Chronic condition with extended duration")
        
        # Normative comparison indicators
        if vald_data.age_matched_percentile and vald_data.age_matched_percentile < 25:
            indicators.append("Below-average physical capacity for age group")
        
        # Movement pattern indicators
        if vald_data.compensation_patterns:
            indicators.append("Movement compensation patterns present")
        
        return indicators

    def _create_enhanced_fallback_analysis(self, vald_data: VALDAssessment, clinical_findings: ClinicalFindings, 
                                         evidence_findings: EvidenceBasedFindings, existing_diagnosis: str) -> PrognosisAnalysis:
        """Create enhanced fallback analysis when AI fails."""
        
        diagnosis = existing_diagnosis or f"{clinical_findings.primary_joint} dysfunction"
        tier = self._infer_probability_tier(vald_data, clinical_findings, existing_diagnosis)
        tier_labels = {1: "Very Unlikely", 2: "Unlikely", 3: "Plausible", 4: "Likely", 5: "Very Likely"}
        
        return PrognosisAnalysis(
            intake_snapshot=f"{clinical_findings.primary_joint} complaint — {clinical_findings.clinical_stage} stage. {clinical_findings.subjective_notes[:200] if clinical_findings.subjective_notes else 'No subjective notes available.'}",
            biomechanical_summary=self._interpret_comprehensive_vald_findings(vald_data),
            force_production_analysis="Limited force production data available — AI analysis unavailable",
            biomechanical_deficits=["Insufficient data for full biomechanical analysis"],
            vald_supports_diagnosis=False,
            provisional_diagnosis=diagnosis,
            diagnostic_bucket=DiagnosticBucket(
                primary_bucket=clinical_findings.functional_region or "Musculoskeletal",
                secondary_bucket=None,
                bucket_reasoning="Assigned from available clinical region data — AI unavailable"
            ),
            probability_tier=ProbabilityTier(
                tier=tier,
                label=tier_labels.get(tier, "Plausible"),
                rationale="Tier inferred from available clinical and VALD data — AI analysis unavailable"
            ),
            why_not_higher_tier="AI analysis unavailable; tier based on heuristic inference only",
            diagnostic_sufficiency=DiagnosticSufficiency(
                is_sufficient=False,
                sufficiency_answer="No — AI analysis unavailable; manual clinical review required",
                driver_systems=[],
                why_not_sufficient="AI analysis failed; cannot assess convergence of intake, objective, and biomechanical data"
            ),
            differential_diagnoses=self._generate_tiered_differentials(clinical_findings, vald_data),
            decision_changing_missing_data=self._identify_decision_changing_missing_data(clinical_findings, vald_data),
            research_evidence=evidence_findings,
            risk_factors=self._identify_comprehensive_risk_factors(clinical_findings, vald_data),
            protective_factors=self._identify_protective_factors(clinical_findings, vald_data),
            expected_recovery_timeline=self._estimate_recovery_timeline(clinical_findings, vald_data),
            return_to_activity_probability="Unable to determine without AI analysis",
            recommended_interventions=self._generate_interventions(clinical_findings, vald_data),
            contraindicated_activities=self._identify_contraindicated_activities(clinical_findings, vald_data),
            red_flags=self._identify_red_flags(clinical_findings),
            follow_up_vald_recommended=True,
            monitoring_parameters=self._generate_comprehensive_monitoring_parameters(vald_data),
            reassessment_timeline=self._determine_reassessment_timeline(clinical_findings, vald_data),
            positioning_summary={
                "provisional_bucket": clinical_findings.functional_region or "Musculoskeletal",
                "probability": tier_labels.get(tier, "Plausible"),
                "sufficiency": "Insufficient — AI unavailable",
                "competing_drivers": "Unknown — manual review required",
                "additional_data_required": "Full AI analysis required"
            }
        )

    def _interpret_vald_findings(self, vald_data: VALDAssessment) -> str:
        """Interpret VALD assessment findings."""
        
        findings = []
        
        if vald_data.strength_asymmetry_percent is not None:
            if vald_data.strength_asymmetry_percent > 20:
                findings.append(f"Significant strength asymmetry ({vald_data.strength_asymmetry_percent:.1f}%) indicating substantial functional deficit")
            elif vald_data.strength_asymmetry_percent > 15:
                findings.append(f"Moderate strength asymmetry ({vald_data.strength_asymmetry_percent:.1f}%) requiring targeted intervention")
            else:
                findings.append(f"Minimal strength asymmetry ({vald_data.strength_asymmetry_percent:.1f}%) within acceptable range")
        
        if vald_data.rom_asymmetry_degrees is not None:
            if vald_data.rom_asymmetry_degrees > 10:
                findings.append(f"Significant ROM asymmetry ({vald_data.rom_asymmetry_degrees}°)")
            else:
                findings.append(f"ROM asymmetry within normal limits ({vald_data.rom_asymmetry_degrees}°)")
        
        if vald_data.absolute_force_level:
            findings.append(f"Absolute force level: {vald_data.absolute_force_level}")
        
        if vald_data.is_first_assessment:
            findings.append("First VALD assessment provides important baseline for monitoring progress")
        
        return "; ".join(findings) if findings else "Limited VALD data available"

    def _extract_key_indicators(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Extract key clinical indicators."""
        
        indicators = []
        
        # Clinical indicators
        if clinical_findings.duration_months and clinical_findings.duration_months > 12:
            indicators.append("Chronic condition (>12 months)")
        
        # VALD indicators
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 15:
            indicators.append("Significant strength asymmetry")
        
        if vald_data.absolute_force_level == "Low":
            indicators.append("Reduced force production capacity")
        
        # Pattern recognition from subjective notes
        if "pain" in clinical_findings.subjective_notes.lower():
            indicators.append("Pain-related movement dysfunction")
        
        return indicators

    def _estimate_recovery_timeline(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> str:
        """Estimate recovery timeline based on clinical and VALD data."""
        
        base_timeline = {
            "acute": "2-6 weeks",
            "subacute": "6-12 weeks", 
            "chronic": "12-24 weeks"
        }
        
        timeline = base_timeline.get(clinical_findings.clinical_stage, "8-16 weeks")
        
        # Modify based on VALD findings
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 25:
            timeline += " (extended due to significant strength deficits)"
        elif vald_data.absolute_force_level == "Low":
            timeline += " (may require additional strength phase)"
        
        return timeline

    def _generate_interventions(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Generate recommended interventions."""
        
        interventions = ["Manual therapy and movement re-education"]
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 15:
            interventions.append("Targeted strength training for asymmetry correction")
        
        if vald_data.absolute_force_level == "Low":
            interventions.append("Progressive strength and conditioning program")
        
        if clinical_findings.clinical_stage == "chronic":
            interventions.append("Pain science education and graded exposure")
        
        interventions.append("Regular VALD reassessment to monitor progress")
        
        return interventions

    def _identify_red_flags(self, clinical_findings: ClinicalFindings) -> List[str]:
        """Identify potential red flags."""
        
        red_flags = []
        
        # Check for concerning patterns in history/notes
        concerning_terms = ["trauma", "fracture", "neurological", "bowel", "bladder", "fever"]
        
        combined_text = (clinical_findings.clinical_history + " " + clinical_findings.subjective_notes).lower()
        
        for term in concerning_terms:
            if term in combined_text:
                red_flags.append(f"Potential {term}-related concern mentioned")
        
        return red_flags

    def _generate_differentials(self, clinical_findings: ClinicalFindings) -> List[str]:
        """Generate differential diagnoses."""
        
        differentials = []
        
        # Based on joint/region
        if "spine" in clinical_findings.functional_region.lower():
            differentials.extend(["Discogenic pain", "Facet joint dysfunction", "Myofascial pain"])
        elif "knee" in clinical_findings.primary_joint.lower():
            differentials.extend(["Patellofemoral pain", "Meniscal pathology", "Ligament strain"])
        elif "shoulder" in clinical_findings.primary_joint.lower():
            differentials.extend(["Rotator cuff pathology", "Impingement syndrome", "Adhesive capsulitis"])
        
        return differentials[:3]  # Limit to top 3

    def _generate_monitoring_parameters(self, vald_data: VALDAssessment) -> List[str]:
        """Generate parameters to monitor during treatment."""
        
        parameters = ["Pain levels (NPRS)", "Functional capacity"]
        
        if vald_data.strength_asymmetry_percent is not None:
            parameters.append("Strength asymmetry percentage")
        
        if vald_data.rom_asymmetry_degrees is not None:
            parameters.append("ROM asymmetry")
        
        if vald_data.absolute_force_level:
            parameters.append("Absolute force production")
        
        parameters.append("Return to activity milestones")
        
        return parameters

    def _create_fallback_analysis(self, vald_data: VALDAssessment, clinical_findings: ClinicalFindings, 
                                existing_diagnosis: str) -> PrognosisAnalysis:
        """Create fallback analysis when AI fails."""
        
        diagnosis = existing_diagnosis or f"{clinical_findings.primary_joint} dysfunction"
        tier = self._infer_probability_tier(vald_data, clinical_findings, existing_diagnosis)
        tier_labels = {1: "Very Unlikely", 2: "Unlikely", 3: "Plausible", 4: "Likely", 5: "Very Likely"}
        
        return PrognosisAnalysis(
            intake_snapshot=f"{clinical_findings.primary_joint} complaint — {clinical_findings.clinical_stage} stage.",
            biomechanical_summary=self._interpret_vald_findings(vald_data),
            force_production_analysis="Force production data not available for this analysis",
            biomechanical_deficits=["Insufficient data for biomechanical analysis"],
            vald_supports_diagnosis=False,
            provisional_diagnosis=diagnosis,
            diagnostic_bucket=DiagnosticBucket(
                primary_bucket=clinical_findings.functional_region or "Musculoskeletal",
                secondary_bucket=None,
                bucket_reasoning="Assigned from available clinical region data"
            ),
            probability_tier=ProbabilityTier(
                tier=tier,
                label=tier_labels.get(tier, "Plausible"),
                rationale="Tier inferred from available data — AI analysis unavailable"
            ),
            why_not_higher_tier="AI analysis unavailable",
            diagnostic_sufficiency=DiagnosticSufficiency(
                is_sufficient=False,
                sufficiency_answer="No — insufficient data for convergence assessment",
                driver_systems=[],
                why_not_sufficient="AI analysis failed; manual clinical review required"
            ),
            differential_diagnoses=self._generate_tiered_differentials(clinical_findings, vald_data),
            decision_changing_missing_data=self._identify_decision_changing_missing_data(clinical_findings, vald_data),
            research_evidence=EvidenceBasedFindings(
                condition_prevalence="Unknown",
                evidence_based_interventions=["Comprehensive assessment recommended"],
                prognostic_factors=["Insufficient data"],
                return_to_sport_rates="Unknown",
                recurrence_rates="Unknown"
            ),
            risk_factors=self._identify_comprehensive_risk_factors(clinical_findings, vald_data),
            protective_factors=self._identify_protective_factors(clinical_findings, vald_data),
            expected_recovery_timeline=self._estimate_recovery_timeline(clinical_findings, vald_data),
            return_to_activity_probability="Unable to determine without AI analysis",
            recommended_interventions=self._generate_interventions(clinical_findings, vald_data),
            contraindicated_activities=["Consult healthcare provider"],
            red_flags=self._identify_red_flags(clinical_findings),
            follow_up_vald_recommended=True,
            monitoring_parameters=self._generate_monitoring_parameters(vald_data),
            reassessment_timeline="4-6 weeks",
            positioning_summary={
                "provisional_bucket": clinical_findings.functional_region or "Musculoskeletal",
                "probability": tier_labels.get(tier, "Plausible"),
                "sufficiency": "Insufficient",
                "competing_drivers": "Unknown",
                "additional_data_required": "Full clinical assessment required"
            }
        )


# Rebuild Pydantic models
VALDAssessment.model_rebuild()
ClinicalFindings.model_rebuild()
EvidenceBasedFindings.model_rebuild()
PrognosisAnalysis.model_rebuild()


def analyze_patient_from_file(patient_id: str, test_file_path: str = None) -> PrognosisAnalysis:
    """Analyze a specific patient from the test data file."""
    
    if not test_file_path:
        test_file_path = Path(__file__).parent / "test.json"
    
    try:
        with open(test_file_path, 'r') as f:
            patients = json.load(f)
        
        # Find patient by ID
        patient_data = None
        for patient in patients:
            if patient.get("patient_id") == patient_id:
                patient_data = patient
                break
        
        if not patient_data:
            raise ValueError(f"Patient {patient_id} not found in test data")
        
        # Initialize agent and analyze
        agent = ClinicalPrognosisAgent()
        analysis = agent.analyze_patient_prognosis(patient_data)
        
        return analysis
        
    except Exception as e:
        print(f"❌ Error analyzing patient {patient_id}: {e}")
        raise


if __name__ == "__main__":
    # Test with a sample patient
    try:
        # Use the first patient from test data
        test_file = Path(__file__).parent / "test.json"
        with open(test_file, 'r') as f:
            patients = json.load(f)
        
        if patients:
            patient_id = patients[0]["patient_id"]
            print(f"🔍 Analyzing patient: {patient_id}")
            
            analysis = analyze_patient_from_file(patient_id)
            
            print(f"\n📋 PROGNOSIS ANALYSIS:")
            print(f"Provisional Diagnosis: {analysis.provisional_diagnosis}")
            print(f"Tier: {analysis.probability_tier.tier}/5 — {analysis.probability_tier.label}")
            print(f"Biomechanical Summary: {analysis.biomechanical_summary}")
            print(f"Recovery Timeline: {analysis.expected_recovery_timeline}")
            print(f"Key Interventions: {', '.join(analysis.recommended_interventions)}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")