import * as vscode from 'vscode';

const RESERVED_COMPONENT_KEYS = new Set([
  'id',
  'type',
  'description',
  'version',
  'kind',
  'metadata',
  'tags',
  'owner'
]);

export function validateDistributions(document: vscode.TextDocument): vscode.Diagnostic[] {
  const diagnostics: vscode.Diagnostic[] = [];
  const text = document.getText();

  validateBernoulliRanges(document, text, diagnostics);
  validateReferences(document, text, diagnostics);
  validateBasicQueryForms(document, text, diagnostics);

  return diagnostics;
}

function validateBernoulliRanges(
  document: vscode.TextDocument,
  text: string,
  diagnostics: vscode.Diagnostic[]
): void {
  const bernoulliRegex = /Bernoulli\(([^)]+)\)/g;
  let match: RegExpExecArray | null;

  while ((match = bernoulliRegex.exec(text)) !== null) {
    const raw = match[1].trim();
    const prob = Number(raw);
    if (Number.isNaN(prob) || prob < 0 || prob > 1) {
      diagnostics.push(
        new vscode.Diagnostic(
          new vscode.Range(document.positionAt(match.index), document.positionAt(match.index + match[0].length)),
          `Invalid Bernoulli parameter '${raw}'. Expected a numeric probability in [0, 1].`,
          vscode.DiagnosticSeverity.Error
        )
      );
    }
  }
}

function validateReferences(
  document: vscode.TextDocument,
  text: string,
  diagnostics: vscode.Diagnostic[]
): void {
  const declared = collectDeclaredVariables(text);
  const referenceRegex = /(source|target):\s*([A-Za-z_][A-Za-z0-9_.]*)/g;
  let match: RegExpExecArray | null;

  while ((match = referenceRegex.exec(text)) !== null) {
    const ref = match[2];
    if (!declared.has(ref)) {
      diagnostics.push(
        new vscode.Diagnostic(
          new vscode.Range(document.positionAt(match.index), document.positionAt(match.index + match[0].length)),
          `Undefined variable reference '${ref}'. Declare it under components or exogenous.`,
          vscode.DiagnosticSeverity.Error
        )
      );
    }
  }

  const doRegex = /do\(([^=]+)=([^\)]+)\)/g;
  while ((match = doRegex.exec(text)) !== null) {
    const ref = match[1].trim();
    if (!declared.has(ref)) {
      diagnostics.push(
        new vscode.Diagnostic(
          new vscode.Range(document.positionAt(match.index), document.positionAt(match.index + match[0].length)),
          `Undefined intervention variable '${ref}' in do(...).`,
          vscode.DiagnosticSeverity.Error
        )
      );
    }
  }
}

function validateBasicQueryForms(
  document: vscode.TextDocument,
  text: string,
  diagnostics: vscode.Diagnostic[]
): void {
  const queryRegex = /query:\s*([^\n]+)/g;
  let match: RegExpExecArray | null;

  while ((match = queryRegex.exec(text)) !== null) {
    const query = match[1].trim();
    if (!/^([PE])\(.+\)$/.test(query)) {
      diagnostics.push(
        new vscode.Diagnostic(
          new vscode.Range(document.positionAt(match.index), document.positionAt(match.index + match[0].length)),
          `Unsupported query syntax '${query}'. Use P(...) or E(...).`,
          vscode.DiagnosticSeverity.Warning
        )
      );
    }
  }
}

function collectDeclaredVariables(text: string): Set<string> {
  const variables = new Set<string>();
  const lines = text.split(/\r?\n/);
  let currentComponentId: string | null = null;
  let inComponents = false;
  let inExogenous = false;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\t/g, '    ');
    const trimmed = line.trim();

    if (trimmed.startsWith('components:')) {
      inComponents = true;
      inExogenous = false;
      currentComponentId = null;
      continue;
    }
    if (trimmed.startsWith('exogenous:')) {
      inComponents = false;
      inExogenous = true;
      currentComponentId = null;
      continue;
    }
    if (/^(causal_links|counterfactuals|connectors):/.test(trimmed)) {
      inComponents = false;
      inExogenous = false;
      currentComponentId = null;
      continue;
    }

    if (inComponents) {
      const idMatch = trimmed.match(/^-\s+id:\s*([A-Za-z_][A-Za-z0-9_]*)$/) || trimmed.match(/^id:\s*([A-Za-z_][A-Za-z0-9_]*)$/);
      if (idMatch) {
        currentComponentId = idMatch[1];
        continue;
      }
      const propMatch = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*:/);
      if (propMatch && currentComponentId && !RESERVED_COMPONENT_KEYS.has(propMatch[1])) {
        variables.add(`${currentComponentId}.${propMatch[1]}`);
      }
      continue;
    }

    if (inExogenous) {
      const idMatch = trimmed.match(/^-\s+id:\s*([A-Za-z_][A-Za-z0-9_]*)$/) || trimmed.match(/^id:\s*([A-Za-z_][A-Za-z0-9_]*)$/);
      if (idMatch) {
        variables.add(idMatch[1]);
        continue;
      }
      const inlineMatch = trimmed.match(/^-\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/);
      if (inlineMatch && inlineMatch[1] !== 'distribution') {
        variables.add(inlineMatch[1]);
      }
    }
  }

  return variables;
}
