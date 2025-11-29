// src/linter.ts
import * as vscode from 'vscode';

// Validates that probability distributions in CausalLinks sum to 1.0
export function validateDistributions(document: vscode.TextDocument): vscode.Diagnostic[] {
    const diagnostics: vscode.Diagnostic[] = [];
    const text = document.getText();
    
    // Regex to find Bernoulli definitions like: failure_rate: Bernoulli(1.2)
    const bernoulliRegex = /Bernoulli\(([^)]+)\)/g;
    let match;

    while ((match = bernoulliRegex.exec(text)) !== null) {
        const prob = parseFloat(match[1]);
        if (prob < 0 || prob > 1) {
            const range = new vscode.Range(
                document.positionAt(match.index), 
                document.positionAt(match.index + match[0].length)
            );
            const diagnostic = new vscode.Diagnostic(
                range, 
                `Invalid probability: ${prob}. Must be between 0 and 1.`, 
                vscode.DiagnosticSeverity.Error
            );
            diagnostics.push(diagnostic);
        }
    }
    return diagnostics;
}
