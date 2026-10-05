#!/usr/bin/env bun
// todo.js — a tiny todo CLI that ships with exactly two bugs.
// Blind-test target: reproduce both via the CLI, then fix the code.
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const FILE = new URL("./todos.json", import.meta.url);
const load = () => (existsSync(FILE) ? JSON.parse(readFileSync(FILE)) : []);
const save = (t) => writeFileSync(FILE, JSON.stringify(t, null, 2));

const [, , cmd, ...args] = process.argv;
let todos = load();

switch (cmd) {
  case "add": {
    todos.push({ id: todos.length + 1, text: args.join(" "), done: false });
    save(todos);
    console.log("added:", args.join(" "));
    break;
  }
  case "list": {
    for (const t of todos) console.log(`${t.done ? "x" : " "} [${t.id}] ${t.text}`);
    break;
  }
  case "done": {
    const t = todos.find((t) => t.id === args[0]);
    if (t) {
      t.done = true;
      save(todos);
      console.log("done:", t.text);
    }
    break;
  }
  case "rm": {
    const idx = todos.findIndex((t) => Number(t.id) === parseInt(args[0]));
    if (idx >= 0) todos.splice(idx);
    save(todos);
    break;
  }
  default:
    console.log("usage: bun todo.js add|list|done|rm <args>");
}
