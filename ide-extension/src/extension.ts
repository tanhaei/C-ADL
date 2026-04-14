import * as vscode from 'vscode';
import { validateDistributions } from './linter';

let diagnosticCollection: vscode.DiagnosticCollection;

export function activate(context: vscode.ExtensionContext) {
  diagnosticCollection = vscode.languages.createDiagnosticCollection('cadl');
  context.subscriptions.push(diagnosticCollection);

  const compileCommand = vscode.commands.registerCommand('cadl.compile', () => {
    vscode.window.showInformationMessage('C-ADL: validated YAML front-end and prepared model for compilation.');
  });

  const visualizeCommand = vscode.commands.registerCommand('cadl.visualize', () => {
    vscode.window.showInformationMessage('C-ADL: use the Mermaid/visualization backend from the compiler to render the causal graph.');
  });

  context.subscriptions.push(compileCommand, visualizeCommand);

  if (vscode.window.activeTextEditor) {
    updateDiagnostics(vscode.window.activeTextEditor.document);
  }

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument(updateDiagnostics),
    vscode.workspace.onDidChangeTextDocument(event => updateDiagnostics(event.document)),
    vscode.window.onDidChangeActiveTextEditor(editor => {
      if (editor) {
        updateDiagnostics(editor.document);
      }
    })
  );
}

function updateDiagnostics(document: vscode.TextDocument) {
  if (document.languageId === 'yaml' || document.languageId === 'cadl') {
    diagnosticCollection.set(document.uri, validateDistributions(document));
  }
}

export function deactivate() {
  diagnosticCollection?.dispose();
}
