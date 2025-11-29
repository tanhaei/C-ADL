import * as vscode from 'vscode';
// Import the validation logic defined in the previous step (linter.ts)
import { validateDistributions } from './linter';

// This reference enables us to clear diagnostics when the extension is deactivated
let diagnosticCollection: vscode.DiagnosticCollection;

export function activate(context: vscode.ExtensionContext) {
    console.log('C-ADL Extension is now active!');

    // 1. Create a DiagnosticCollection to report errors (red squiggly lines)
    diagnosticCollection = vscode.languages.createDiagnosticCollection('cadl');
    context.subscriptions.push(diagnosticCollection);

    // 2. Register the 'Compile' command (simulates translation to Alloy/pgmpy)
    const compileCommand = vscode.commands.registerCommand('cadl.compile', () => {
        vscode.window.showInformationMessage('Compiling C-ADL model to SCM and Alloy...');
        // In a real implementation, this would call the Python backend
    });
    context.subscriptions.push(compileCommand);

    // 3. Event Listener: Validate on File Open
    if (vscode.window.activeTextEditor) {
        updateDiagnostics(vscode.window.activeTextEditor.document);
    }

    // 4. Event Listener: Validate on File Change
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(editor => {
            if (editor) {
                updateDiagnostics(editor.document);
            }
        })
    );

    // 5. Event Listener: Validate on File Switch
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(editor => {
            if (editor) {
                updateDiagnostics(editor.document);
            }
        })
    );
}

// Helper function to run validation and update UI
function updateDiagnostics(document: vscode.TextDocument) {
    // Only validate .yaml or .cadl files
    if (document.languageId === 'yaml' || document.languageId === 'cadl') {
        const diagnostics = validateDistributions(document);
        diagnosticCollection.set(document.uri, diagnostics);
    } else {
        diagnosticCollection.clear();
    }
}

export function deactivate() {
    if (diagnosticCollection) {
        diagnosticCollection.clear();
        diagnosticCollection.dispose();
    }
}
