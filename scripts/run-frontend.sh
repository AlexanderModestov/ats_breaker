#!/bin/bash
# Run the Next.js frontend development server

set -e

cd "$(dirname "$0")/../frontend"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    npm install
fi

# Run Next.js dev server
npm run dev
