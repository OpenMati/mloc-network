#!/bin/bash
# Test script for /api/v1/tasks/simple endpoint

set -e

ORCHESTRATOR_URL="http://localhost:8000"
TOKEN="${ORCHESTRATOR_TOKEN:-}"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}➜ $1${NC}"
}

# Function to make authenticated requests
make_request() {
    local method=$1
    local endpoint=$2
    local data=$3
    
    if [ -n "$TOKEN" ]; then
        curl -s -X "$method" "$ORCHESTRATOR_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $TOKEN" \
            -d "$data"
    else
        curl -s -X "$method" "$ORCHESTRATOR_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data"
    fi
}

echo "============================================"
echo "Testing /api/v1/tasks/simple API"
echo "============================================"
echo ""

# Test 1: Simple hello-world task
print_info "Test 1: Submitting hello-world task"
RESPONSE=$(make_request POST "/api/v1/tasks/simple" '{
  "taskType": "hello-world",
  "input": {
    "name": "Alice"
  }
}')

TASK_ID_1=$(echo "$RESPONSE" | jq -r '.tasks[0].task_id')
if [ "$TASK_ID_1" != "null" ] && [ -n "$TASK_ID_1" ]; then
    print_success "Task submitted successfully: $TASK_ID_1"
    echo "$RESPONSE" | jq '.'
else
    print_error "Failed to submit task"
    echo "$RESPONSE"
    exit 1
fi
echo ""

# Test 2: Task with tags
print_info "Test 2: Submitting task with tags"
RESPONSE=$(make_request POST "/api/v1/tasks/simple" '{
  "taskType": "hello-world",
  "input": {
    "name": "Bob"
  },
  "tags": ["test", "development"]
}')

TASK_ID_2=$(echo "$RESPONSE" | jq -r '.tasks[0].task_id')
if [ "$TASK_ID_2" != "null" ] && [ -n "$TASK_ID_2" ]; then
    print_success "Task with tags submitted: $TASK_ID_2"
    echo "$RESPONSE" | jq '.tasks[0]'
else
    print_error "Failed to submit task with tags"
    echo "$RESPONSE"
fi
echo ""

# Test 3: Task with SLO
print_info "Test 3: Submitting task with SLO (60 seconds)"
RESPONSE=$(make_request POST "/api/v1/tasks/simple" '{
  "taskType": "hello-world",
  "input": {
    "name": "Charlie"
  },
  "sloSeconds": 60
}')

TASK_ID_3=$(echo "$RESPONSE" | jq -r '.tasks[0].task_id')
if [ "$TASK_ID_3" != "null" ] && [ -n "$TASK_ID_3" ]; then
    print_success "Task with SLO submitted: $TASK_ID_3"
    echo "$RESPONSE" | jq '.tasks[0]'
else
    print_error "Failed to submit task with SLO"
    echo "$RESPONSE"
fi
echo ""

# Test 4: Complex input data
print_info "Test 4: Submitting task with complex input"
RESPONSE=$(make_request POST "/api/v1/tasks/simple" '{
  "taskType": "hello-world",
  "input": {
    "name": "David",
    "greeting": "Hello",
    "metadata": {
      "timestamp": "2025-01-23T10:00:00Z",
      "version": "1.0"
    }
  },
  "tags": ["production", "priority-high"],
  "sloSeconds": 30
}')

TASK_ID_4=$(echo "$RESPONSE" | jq -r '.tasks[0].task_id')
if [ "$TASK_ID_4" != "null" ] && [ -n "$TASK_ID_4" ]; then
    print_success "Complex task submitted: $TASK_ID_4"
    echo "$RESPONSE" | jq '{task_id: .tasks[0].task_id, status: .tasks[0].status, generated_yaml: .generated_yaml}'
else
    print_error "Failed to submit complex task"
    echo "$RESPONSE"
fi
echo ""

# Test 5: Check generated YAML
print_info "Test 5: Viewing generated YAML for last task"
echo "$RESPONSE" | jq -r '.generated_yaml'
echo ""

# Test 6: Invalid task type (should still work, but won't match any worker)
print_info "Test 6: Submitting task with non-existent taskType"
RESPONSE=$(make_request POST "/api/v1/tasks/simple" '{
  "taskType": "non-existent-type",
  "input": {
    "test": "data"
  }
}')

if echo "$RESPONSE" | jq -e '.ok' > /dev/null 2>&1; then
    TASK_ID_5=$(echo "$RESPONSE" | jq -r '.tasks[0].task_id')
    print_success "Task accepted (will wait for matching worker): $TASK_ID_5"
    echo "$RESPONSE" | jq '.tasks[0]'
else
    print_error "Request failed"
    echo "$RESPONSE"
fi
echo ""

# Wait for tasks to complete
print_info "Waiting 3 seconds for tasks to complete..."
sleep 3
echo ""

# Check results for first task
print_info "Checking result for Task 1: $TASK_ID_1"
if [ -n "$TOKEN" ]; then
    RESULT=$(curl -s "$ORCHESTRATOR_URL/api/v1/results/$TASK_ID_1" \
        -H "Authorization: Bearer $TOKEN")
else
    RESULT=$(curl -s "$ORCHESTRATOR_URL/api/v1/results/$TASK_ID_1")
fi

if echo "$RESULT" | jq -e '.result' > /dev/null 2>&1; then
    print_success "Result retrieved successfully"
    echo "$RESULT" | jq '{task_id, worker_id, result}'
else
    print_error "Result not found (task may still be running)"
    echo "$RESULT" | jq '.'
fi
echo ""

# List all tasks
print_info "Listing all tasks"
if [ -n "$TOKEN" ]; then
    ALL_TASKS=$(curl -s "$ORCHESTRATOR_URL/api/v1/tasks" \
        -H "Authorization: Bearer $TOKEN")
else
    ALL_TASKS=$(curl -s "$ORCHESTRATOR_URL/api/v1/tasks")
fi

TASK_COUNT=$(echo "$ALL_TASKS" | jq '. | length')
print_success "Total tasks in system: $TASK_COUNT"
echo "$ALL_TASKS" | jq '[.[] | {task_id, status, task_type, assigned_worker}] | .[:5]'
echo ""

# List workers
print_info "Listing available workers"
if [ -n "$TOKEN" ]; then
    WORKERS=$(curl -s "$ORCHESTRATOR_URL/workers" \
        -H "Authorization: Bearer $TOKEN")
else
    WORKERS=$(curl -s "$ORCHESTRATOR_URL/workers")
fi

WORKER_COUNT=$(echo "$WORKERS" | jq '. | length')
print_success "Total workers available: $WORKER_COUNT"
echo "$WORKERS" | jq '[.[] | {worker_id, status, task_types_json, tags_json}]'
echo ""

echo "============================================"
print_success "All tests completed!"
echo "============================================"
echo ""
echo "Summary:"
echo "  Task 1 (basic):     $TASK_ID_1"
echo "  Task 2 (tags):      $TASK_ID_2"
echo "  Task 3 (SLO):       $TASK_ID_3"
echo "  Task 4 (complex):   $TASK_ID_4"
echo ""
echo "To check individual task status:"
echo "  curl $ORCHESTRATOR_URL/api/v1/tasks/{task_id}"
echo ""
echo "To get task result:"
echo "  curl $ORCHESTRATOR_URL/api/v1/results/{task_id}"
