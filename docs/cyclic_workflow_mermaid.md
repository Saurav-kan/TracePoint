# Cyclic Workflow Graph

This diagram reflects the current backend workflow implementation: the planner builds the first task set, research gathers evidence, the judge decides whether evidence is sufficient, and refinement loops continue until the judge is satisfied or the effort budget is exhausted.

```mermaid
flowchart TD
    Client[Frontend or API client] --> RunSync["POST /workflow/run"]
    Client --> RunStream["POST /workflow/run-stream"]
    Client --> LogList["GET /workflow/logs/{case_id}"]
    Client --> LogDetail["GET /workflow/logs/{case_id}/{log_id}"]

    subgraph Entry["Router Setup"]
        RunSync --> ResolveBrief["Resolve case + optional brief override"]
        RunStream --> ResolveBrief
        ResolveBrief --> BuildState["Build PipelineState\n- case\n- request\n- brief_text_override\n- max_iterations\n- iterations=[]"]
    end

    subgraph Graph["Compiled LangGraph Workflow"]
        BuildState --> PlannerNode["planner_node"]

        subgraph PlannerPass["Planner Pass"]
            PlannerNode --> PlannerMode{"Refinement context present?"}
            PlannerMode -- No --> PlannerAttempt["run_planner()\nGenerate 10 initial tasks"]
            PlannerAttempt --> GateCheck["validate_planner_output()"]
            GateCheck --> PlannerRetry{"Valid?"}
            PlannerRetry -- No, attempts remain --> PlannerAttempt
            PlannerRetry -- No, attempts exhausted --> PlannerError["Raise workflow error"]
            PlannerRetry -- Yes --> PlannerOut["Store planner_result + gatekeeper_result"]

            PlannerMode -- Yes --> RefinementPlan["run_planner(..., refinement_context=judge_questions)\nGenerate 1-3 supplemental tasks"]
            RefinementPlan --> GateBypass["Synthetic gatekeeper pass\nReason: refinement bypasses 10-task checks"]
            GateBypass --> PlannerOut
        end

        PlannerOut --> GatekeeperNode["gatekeeper_node\nEmit gatekeeper step for streaming/UI"]
        GatekeeperNode --> ResearchNode["research_node"]

        subgraph ResearchPass["Research Pass"]
            ResearchNode --> ResearchExec["run_research(planner_result)\n- embed vector_query\n- apply case/time/metadata filters\n- fetch ranked snippets\n- attach neighbor context"]
        end

        ResearchExec --> JudgeNode["judge_node"]

        subgraph JudgePass["Judge Pass"]
            JudgeNode --> JudgeExec["run_judge(research_result, case_brief_override)\n- assess each task\n- build overall verdict\n- derive needs_refinement + refinement_questions"]
            JudgeExec --> SaveIteration["Append WorkflowIteration\n- planner\n- gatekeeper\n- research\n- judge"]
            SaveIteration --> JudgeDecision{"Judge requests refinement\nand iterations < max_iterations?"}
            JudgeDecision -- Yes --> BuildRefinement["Build refinement_context from\njudge.refinement_questions\nand judge.refinement_suggestion"]
            BuildRefinement --> PlannerNode
            JudgeDecision -- No --> FinalVerdict["Set final_verdict"]
        end
    end

    FinalVerdict --> SyncReturn["Return JudgeResponse from /workflow/run"]

    subgraph Streaming["Streaming + Persistence"]
        PlannerOut --> SSEPlanner["SSE step: planner"]
        GatekeeperNode --> SSEGate["SSE step: gatekeeper"]
        ResearchExec --> SSEResearch["SSE step: research"]
        JudgeExec --> SSEJudge["SSE step: judge"]
        FinalVerdict --> BuildResponse["Build WorkflowResponse\n- log_id\n- effort_level\n- iterations[]\n- final_verdict"]
        BuildResponse --> Persist["Persist InvestigationLog.result_payload"]
        Persist --> DoneEvent["SSE done event with WorkflowResponse"]
    end

    LogList --> LogSummary["Return InvestigationLogSummary[]"]
    LogDetail --> StoredPayload["Return stored WorkflowResponse payload"]

    classDef api fill:#e3f2fd,stroke:#1e88e5,stroke-width:1px,color:#0d47a1;
    classDef graph fill:#f3e5f5,stroke:#8e24aa,stroke-width:1px,color:#4a148c;
    classDef decision fill:#fff3e0,stroke:#fb8c00,stroke-width:1px,color:#e65100;
    classDef data fill:#e8f5e9,stroke:#43a047,stroke-width:1px,color:#1b5e20;
    classDef error fill:#ffebee,stroke:#e53935,stroke-width:1px,color:#b71c1c;

    class Client,RunSync,RunStream,LogList,LogDetail api;
    class BuildState,PlannerNode,GatekeeperNode,ResearchNode,JudgeNode graph;
    class PlannerMode,PlannerRetry,JudgeDecision decision;
    class PlannerOut,ResearchExec,JudgeExec,SaveIteration,BuildRefinement,FinalVerdict,BuildResponse,Persist,DoneEvent,SyncReturn,LogSummary,StoredPayload data;
    class PlannerError error;
```
