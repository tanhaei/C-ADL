# **C-ADL: Causal Architecture Description Language**

**C-ADL** is a novel Architecture Description Language (ADL) designed to bridge the gap between software architecture design and causal inference. It integrates Judea Pearl's Structural Causal Models (SCMs) directly into component-connector architectures, enabling software architects to perform **Root-Cause Analysis (RCA)** and **Counterfactual Reasoning** at design time.

This repository contains the official toolchain, benchmarks, and evaluation datasets for the paper:

**"C-ADL: A Causal Architecture Description Language for Root-Cause Analysis and Counterfactual Reasoning in Software Architectures"**

## **🚀 Key Features**

* **Design-Time Causal Modeling:** Embed SCMs into architectural descriptions using a human-readable YAML syntax.  
* **Intervention Queries (do-calculus):** Simulate "what-if" scenarios (e.g., do(auth.failure=true)) without touching production code.  
* **Counterfactual Reasoning:** Answer retrospective questions like *"Had we increased the timeout, would the outage have occurred?"*.  
* **Formal Verification:** Automated translation to **Alloy 6** for structural validation.  
* **Probabilistic Inference:** Backend integration with **pgmpy** for Bayesian network analysis.  
* **VS Code Support:** A dedicated extension with syntax highlighting, real-time validation, and auto-completion.

## **📂 Repository Structure**

The project is organized as follows to support the complete toolchain:

```
C-ADL-Workbench/  
├── ide-extension/           \# VS Code Extension source code  
│   ├── package.json  
│   ├── src/  
│   │   ├── extension.ts     \# Activation logic  
│   │   └── linter.ts        \# Real-time causal validation logic  
│   └── syntaxes/  
│       └── cadl.tmLanguage.json  
├── compiler/                \# Core compiler (YAML \-\> SCM/Alloy)  
│   ├── cadl\_parser.py  
│   └── svers/               \# pgmpy and Alloy backend solvers  
├── benchmarks/              \# Evaluation Case Studies  
│   ├── TrainTicket/         \# Microservices benchmark models  
│   ├── IoT-Gateway/         \# SmartHome edge scenarios  
│   └── MLOps-Pipeline/      \# Data pipeline models  
├── datasets/                \# Raw traces and chaos experiment data  
│   ├── deathstarbench/      \# Traces from DeathStarBench (Microservices)  
│   └── chaos-logs/          \# Logs from chaos engineering runs  
├── tests/                   \# Integration tests  
│   └── test\_inference.py    \# pgmpy verification tests  
└── visualization/           \# React/D3.js interactive dashboard
```
## **🛠️ Installation & Setup**

### **Prerequisites**

* Python 3.8+  
* Node.js & npm (for VS Code extension and visualizer)  
* [Alloy 6](https://alloytools.org/) (optional, for formal verification)

### **1\. Install the Compiler & Solvers**

```
git clone https://github.com/tanhaei/C-ADL.git
cd C-ADL/compiler  
pip install -r requirements.txt
```

### **2\. Install the VS Code Extension**

You can install the .vsix package from the releases folder or build it from source:

```
cd ide-extension  
npm install  
npm run compile
# Press F5 in VS Code to launch the extension Development Host
```

## **📖 Usage Example**

### **Defining a Model**

Create a .cadl or .yaml file to describe your architecture and causal links. Here is a simplified snippet from the **TrainTicket** benchmark:

```
name: TrainTicket-Causal-Model  
components:  
  - id: auth_service  
    failure_rate: Bernoulli(0.002)  
  - id: order_service  
    latency: Normal(120, 30\) ms

causal_links:  
  - source: auth_service.failure  
    target: ui.login_latency  
    # Structural Equation with Intervention  
    do: do(auth_service.failure=true) -> ui.login_latency=Exponential(8000)

counterfactuals:  
  - id: cf_analysis_01  
    intervention: do(payment.available=false)  
    query: P(order.success | do(payment.available=false))
```

### **Running Analysis**

Use the CLI to compile and query the model:

```
# Verify structural constraints  
python cadl_compiler.py check --model examples/trainticket.yaml --backend alloy

# Run probabilistic inference  
python cadl_compiler.py query --model examples/trainticket.yaml --id cf_analysis_01  
# Output: P(order.success | do(payment.available=false)) = 0.024
```

## **📊 Evaluation & Benchmarks**

We evaluated C-ADL on three systems. The models and data are available in the benchmarks/ directory.

| System | Components | Causal Links | Source Data |  
| TrainTicket | 41 | 68 | DeathStarBench Traces |  
| IoT Edge Gateway | 22 | 44 | Real IoT Logs |  
| MLOps Pipeline | 35 | 59 | GitLab Production Data |  
To reproduce the precision results (83% P@1) reported in the paper:

```
cd tests  
python run_benchmark_eval.py --dataset deathstarbench
```

## **🤝 Contributing**

Contributions are welcome\! Please read CONTRIBUTING.md for details on our code of conduct and the process for submitting pull requests.

1. Fork the repository  
2. Create your feature branch (git checkout -b feature/AmazingFeature)  
3. Commit your changes (git commit -m 'Add some AmazingFeature')  
4. Push to the branch (git push origin feature/AmazingFeature)  
5. Open a Pull Request

## **📄 License**

This project is licensed under the MIT License - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.

## **🔗 Citation**

If you use C-ADL in your research, please cite our paper:

To Appear!

