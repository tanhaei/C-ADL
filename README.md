# **C-ADL: Causal Architecture Description Language**

**C-ADL** is a novel Architecture Description Language (ADL) designed to bridge the gap between software architecture design and causal inference. It integrates Judea Pearl's Structural Causal Models (SCMs) directly into component-connector architectures, enabling software architects to perform **Root-Cause Analysis (RCA)** and **Counterfactual Reasoning** at design time.

This repository contains the official toolchain, benchmarks, and evaluation datasets for the paper:

**"C-ADL: A Causal Architecture Description Language for Root-Cause Analysis and Counterfactual Reasoning in Software Architectures"**

## **🚀 Key Features**

* **Design-Time Causal Modeling:** Embed SCMs into architectural descriptions using a human-readable YAML syntax.  
* **Intervention Queries (do-calculus):** Simulate "what-if" scenarios (e.g., do(auth.failure=true)) without touching production code.  
* **Counterfactual Reasoning:** Answer retrospective questions like *"Had we increased the timeout, would the outage have occurred?"*.  
* **Formal Verification:** Automated translation to **Alloy 6** for structural validation.  
* **Probabilistic Inference:** Backend integration with **pgmpy** for Bayesian network analysis, interventions, and evidence-aware counterfactual approximation.  
* **Typed IR & Mermaid Export:** The compiler normalizes YAML into a typed intermediate representation and can export Mermaid causal graphs for review artifacts.  
* **Progressive Elaboration:** Structure-only and continuous declarations are preserved as structural-only queries when exact numeric inference is not yet supported.  
* **VS Code Support:** A dedicated extension with syntax highlighting, reference checks, real-time validation, and auto-completion.

## **📂 Repository Structure**

The project is organized as follows to support the complete toolchain:

C-ADL-Workbench/  
├── ide-extension/           \# VS Code extension source code  
│   ├── package.json  
│   ├── language-configuration.json  
│   ├── src/  
│   │   ├── extension.ts     \# Activation logic  
│   │   └── linter.ts        \# Real-time causal validation logic  
│   └── syntaxes/  
│       └── cadl.tmLanguage.json  
├── compiler/                \# Core compiler (YAML \-> typed IR / SCM / Alloy)  
│   ├── cadl\_parser.py  
│   ├── cadl\_compiler.py    \# CLI entrypoint for validation/querying  
│   ├── requirements.txt  
│   └── svers/               \# pgmpy, Mermaid, and Alloy backends  
├── benchmarks/              \# Evaluation case studies  
│   ├── TrainTicket/  
│   ├── IoT-Gateway/  
│   └── MLOps-Pipeline/  
├── datasets/                \# Raw traces and chaos experiment data  
├── tests/                   \# Validation + inference tests  
│   └── test\_inference.py  
└── visualization/           \# Interactive dashboards

## **🛠️ Installation & Setup**

### **Prerequisites**

* Python 3.8+  
* Node.js & npm (for VS Code extension and visualizer)  
* [Alloy 6](https://alloytools.org/) (optional, for formal verification)

### **1\. Install the Compiler & Solvers**

git clone \[https://github.com/tanhaei/C-ADL.git\](https://github.com/tanhaei/C-ADL.git)  
cd C-ADL/compiler  
pip install \-r requirements.txt

### **2\. Install the VS Code Extension**

You can install the .vsix package from the releases folder or build it from source:

cd ide-extension  
npm install  
npm run compile  
\# Press F5 in VS Code to launch the extension Development Host

## **📖 Usage Example**

### **Defining a Model**

Create a .cadl or .yaml file to describe your architecture and causal links. Here is a simplified snippet aligned with the paper's typed syntax:

name: TrainTicket-Causal-Model  
components:  
  \- id: auth  
    failure: Bernoulli(0.002)  
  \- id: order  
    db_timeout: Bernoulli(0.01)  
    failure: Bernoulli(0.001)  
  \- id: ui  
    timeout: Bernoulli(0.02)  
    login_latency: Real ms  

exogenous:  
  \- id: network_partition  
    distribution: Bernoulli(0.0005)  

causal\_links:  
  \- source: auth.failure  
    target: ui.timeout  
    prob: 0.95  
  \- source: order.db_timeout  
    target: order.failure  
    prob: 0.90  
  \- source: auth.failure  
    target: ui.login_latency  
    do: do(auth.failure=true) \-> ui.login_latency=Exponential(8000)  

counterfactuals:  
  \- id: q_ui_timeout_if_auth_fails  
    query: P(ui.timeout | do(auth.failure=true))  

### **Running Analysis**

Use the CLI to compile and query the model:

\# Verify structural constraints  
python cadl\_compiler.py check \--model ../benchmarks/TrainTicket/model.cadl

\# Export a Mermaid causal graph  
python cadl\_compiler.py mermaid \--model ../benchmarks/TrainTicket/model.cadl

\# Run an interventional query  
python cadl\_compiler.py intervene \--model ../benchmarks/TrainTicket/model.cadl \--target ui.timeout \--do auth.failure=true

\# Execute a named query from counterfactuals[]  
python cadl\_compiler.py query \--model ../benchmarks/TrainTicket/model.cadl \--query-id q_ui_timeout_if_auth_fails

## **📊 Evaluation, Validation & Benchmarks**

We evaluated C-ADL on three systems. The models and data are available in the benchmarks/ directory.

| System | Components | Causal Links | Source Data |  
| TrainTicket | 41 | 68 | DeathStarBench Traces |  
| IoT Edge Gateway | 22 | 44 | Real IoT Logs |  
| MLOps Pipeline | 35 | 59 | GitLab Production Data |  
The repository now includes benchmark models that follow the paper's typed YAML syntax (components, exogenous variables, causal links, and counterfactual queries), plus unit tests for validation, intervention, and counterfactual execution:

cd tests  
python -m unittest test_inference.py

## **🤝 Contributing**

Contributions are welcome\! Please read CONTRIBUTING.md for details on our code of conduct and the process for submitting pull requests.

1. Fork the repository  
2. Create your feature branch (git checkout \-b feature/AmazingFeature)  
3. Commit your changes (git commit \-m 'Add some AmazingFeature')  
4. Push to the branch (git push origin feature/AmazingFeature)  
5. Open a Pull Request

## **📄 License**

This project is licensed under the MIT License \- see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.

## **🔗 Citation**

If you use C-ADL in your research, please cite our paper:

@article{Tanhaei2025CADL,  
  title={C-ADL: A Causal Architecture Description Language for Root-Cause Analysis and Counterfactual Reasoning},  
  author={Tanhaei, Mohammad},  
  journal={Information and Software Technology},  
  year={2025}  
}

