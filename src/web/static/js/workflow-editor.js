// 工作流编辑器JavaScript
let stepCounter = 0;

// 初始化步骤计数器
document.addEventListener('DOMContentLoaded', function() {
    stepCounter = document.querySelectorAll('.step-card').length;
});

function toggleStep(header) {
    const body = header.nextElementSibling;
    const isVisible = body.style.display !== 'none';
    body.style.display = isVisible ? 'none' : 'block';
}

function addStep() {
    stepCounter++;
    const stepHtml = createStepHtml(stepCounter, 'navigate', '新步骤');
    document.getElementById('stepsContainer').insertAdjacentHTML('beforeend', stepHtml);
    updateStepNumbers();
}

function createStepHtml(index, type, description) {
    const stepTypes = ['navigate', 'click', 'fill', 'select', 'wait', 'scroll', 'hover', 'press_key', 'screenshot', 'extract', 'custom'];
    const stepTypeOptions = stepTypes.map(t => `<option value="${t}" ${t === type ? 'selected' : ''}>${t}</option>`).join('');
    
    return `
        <div class="step-card" data-step-id="new_step_${index}">
            <div class="step-header" onclick="toggleStep(this)">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="badge bg-primary me-2">${index}</span>
                        <strong>${type}</strong>
                        <span class="text-muted ms-2">${description}</span>
                    </div>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-secondary" onclick="moveStepUp(this, event)" title="上移">
                            <i class="bi bi-arrow-up"></i>
                        </button>
                        <button class="btn btn-outline-secondary" onclick="moveStepDown(this, event)" title="下移">
                            <i class="bi bi-arrow-down"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="removeStep(this, event)" title="删除">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
            <div class="step-body" style="display: block;">
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label class="form-label">步骤类型</label>
                            <select class="form-select" name="stepType" title="选择步骤类型">
                                ${stepTypeOptions}
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">描述</label>
                            <input type="text" class="form-control" name="stepDescription" value="${description}">
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label class="form-label">选择器</label>
                            <input type="text" class="form-control" name="stepSelector" value="">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">XPath</label>
                            <input type="text" class="form-control" name="stepXpath" value="">
                        </div>
                    </div>
                </div>
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label class="form-label">URL</label>
                            <input type="text" class="form-control" name="stepUrl" value="">
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label class="form-label">值</label>
                            <input type="text" class="form-control" name="stepValue" value="">
                        </div>
                    </div>
                </div>
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label class="form-label">超时时间(毫秒)</label>
                            <input type="number" class="form-control" name="stepTimeout" value="">
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label class="form-label">等待条件</label>
                            <select class="form-select" name="stepWaitCondition">
                                <option value="">无</option>
                                <option value="visible">可见</option>
                                <option value="hidden">隐藏</option>
                                <option value="enabled">启用</option>
                                <option value="disabled">禁用</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function removeStep(button, event) {
    event.stopPropagation();
    if (confirm('确定要删除这个步骤吗？')) {
        button.closest('.step-card').remove();
        updateStepNumbers();
    }
}

function moveStepUp(button, event) {
    event.stopPropagation();
    const stepCard = button.closest('.step-card');
    const prevStep = stepCard.previousElementSibling;
    if (prevStep) {
        stepCard.parentNode.insertBefore(stepCard, prevStep);
        updateStepNumbers();
    }
}

function moveStepDown(button, event) {
    event.stopPropagation();
    const stepCard = button.closest('.step-card');
    const nextStep = stepCard.nextElementSibling;
    if (nextStep) {
        stepCard.parentNode.insertBefore(nextStep, stepCard);
        updateStepNumbers();
    }
}

function updateStepNumbers() {
    const stepCards = document.querySelectorAll('.step-card');
    stepCards.forEach((card, index) => {
        const badge = card.querySelector('.badge');
        const typeSpan = card.querySelector('.step-header strong');
        const descSpan = card.querySelector('.step-header .text-muted');
        
        badge.textContent = index + 1;
        
        // 更新显示的类型和描述
        const typeSelect = card.querySelector('[name="stepType"]');
        const descInput = card.querySelector('[name="stepDescription"]');
        
        if (typeSelect && typeSpan) {
            typeSpan.textContent = typeSelect.value;
        }
        if (descInput && descSpan) {
            descSpan.textContent = descInput.value || '无描述';
        }
    });
}

function addVariable() {
    const variableHtml = `
        <div class="variable-input">
            <div class="row">
                <div class="col-6">
                    <input type="text" class="form-control form-control-sm" placeholder="变量名" value="">
                </div>
                <div class="col-4">
                    <select class="form-select form-select-sm">
                        <option value="string">字符串</option>
                        <option value="number">数字</option>
                        <option value="boolean">布尔值</option>
                    </select>
                </div>
                <div class="col-2">
                    <button class="btn btn-sm btn-outline-danger" onclick="removeVariable(this)" title="删除变量">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
            <div class="row mt-1">
                <div class="col-6">
                    <input type="text" class="form-control form-control-sm" placeholder="默认值" value="">
                </div>
                <div class="col-6">
                    <input type="text" class="form-control form-control-sm" placeholder="描述" value="">
                </div>
            </div>
        </div>
    `;
    document.getElementById('variablesContainer').insertAdjacentHTML('beforeend', variableHtml);
}

function removeVariable(button) {
    button.closest('.variable-input').remove();
}

async function saveWorkflow() {
    const workflowData = {
        name: document.getElementById('workflowName').value,
        description: document.getElementById('workflowDescription').value,
        version: document.getElementById('workflowVersion').value,
        steps: collectSteps(),
        variables: collectVariables()
    };
    
    try {
        const currentName = window.location.pathname.split('/')[2];
        const response = await fetch(`/api/workflows/${currentName}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(workflowData)
        });
        
        if (response.ok) {
            alert('工作流保存成功！');
            window.location.href = `/workflows/${workflowData.name}`;
        } else {
            const error = await response.json();
            alert('保存失败: ' + error.detail);
        }
    } catch (error) {
        alert('保存失败: ' + error.message);
    }
}

function collectSteps() {
    const steps = [];
    const stepCards = document.querySelectorAll('.step-card');
    
    stepCards.forEach((card, index) => {
        const stepData = {
            id: card.dataset.stepId || `step_${index + 1}`,
            type: card.querySelector('[name="stepType"]').value,
            description: card.querySelector('[name="stepDescription"]').value,
            selector: card.querySelector('[name="stepSelector"]').value,
            xpath: card.querySelector('[name="stepXpath"]').value,
            url: card.querySelector('[name="stepUrl"]').value,
            value: card.querySelector('[name="stepValue"]').value,
            timeout: parseInt(card.querySelector('[name="stepTimeout"]').value) || null,
            wait_condition: card.querySelector('[name="stepWaitCondition"]').value || null
        };
        steps.push(stepData);
    });
    
    return steps;
}

function collectVariables() {
    const variables = {};
    const variableInputs = document.querySelectorAll('.variable-input');
    
    variableInputs.forEach(input => {
        const inputs = input.querySelectorAll('input');
        const select = input.querySelector('select');
        
        const name = inputs[0].value;
        if (name) {
            variables[name] = {
                name: name,
                type: select.value,
                default: inputs[1].value,
                description: inputs[2].value,
                required: false
            };
        }
    });
    
    return variables;
}

// 监听步骤类型和描述变化，实时更新显示
document.addEventListener('change', function(e) {
    if (e.target.name === 'stepType' || e.target.name === 'stepDescription') {
        updateStepNumbers();
    }
});