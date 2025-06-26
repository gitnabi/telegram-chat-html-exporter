// Упрощенный JavaScript для навигации по чату

// Глобальные переменные
let messageIndex = new Map();
let topicMessageMap = new Map();
let isIndexBuilt = false;

document.addEventListener('DOMContentLoaded', () => {
    initializeNavigation();
    buildMessageIndex();
    setupLazyLoading();
    handleInitialNavigation();
    initializeCodeHighlighting();
    setupKeyboardNavigation();
});

// Построение индекса сообщений
function buildMessageIndex() {
    console.log('Построение индекса сообщений...');
    
    messageIndex.clear();
    topicMessageMap.clear();
    
    document.querySelectorAll('section[id^="topic-"]').forEach(section => {
        const topicId = section.id.replace('topic-', '');
        const messages = section.querySelectorAll('.msg[id^="msg-"]');
        
        topicMessageMap.set(topicId, new Set());
        
        messages.forEach(msgElement => {
            const msgId = msgElement.id.replace('msg-', '');
            
            messageIndex.set(msgId, {
                element: msgElement,
                topicId: topicId,
                section: section
            });
            
            topicMessageMap.get(topicId).add(msgId);
        });
    });
    
    isIndexBuilt = true;
    console.log(`Проиндексировано ${messageIndex.size} сообщений в ${topicMessageMap.size} топиках.`);
}

// Инициализация навигации
function initializeNavigation() {
    // Обработчики кликов по табам
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            e.preventDefault();
            const topicId = tab.dataset.id;
            navigateToTopic(topicId);
        });
    });
    
    // Обработка навигации браузера
    window.addEventListener('popstate', handleNavigation);
    
    // Обработка внутренних ссылок на сообщения
    document.addEventListener('click', (e) => {
        const link = e.target.closest('a');
        if (link) {
            const href = link.getAttribute('href');
            if (href && href.startsWith('#msg-')) {
                e.preventDefault();
                navigateToMessage(href.replace('#msg-', ''));
            }
        }
    });
}

// Навигация к топику
function navigateToTopic(topicId, updateHistory = true, scrollToTop = true) {
    // Обновляем активные табы
    document.querySelectorAll('.tab').forEach(tab => {
        const isActive = tab.dataset.id === topicId;
        tab.classList.toggle('bg-github-hover', isActive);
        tab.classList.toggle('border-github-accent', isActive);
    });
    
    // Показываем нужную секцию
    document.querySelectorAll('section[id^="topic-"]').forEach(section => {
        if (section.id === `topic-${topicId}`) {
            section.classList.remove('section-hidden');
        } else {
            section.classList.add('section-hidden');
        }
    });
    
    // Обновляем URL
    if (updateHistory) {
        const newUrl = topicId === '1' ? 
            window.location.pathname : 
            `${window.location.pathname}#topic-${topicId}`;
        history.pushState({ topicId }, '', newUrl);
    }
    
    // Прокрутка наверх
    if (scrollToTop) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// Обработка навигации
function handleNavigation() {
    const hash = window.location.hash;
    
    if (hash.startsWith('#msg-')) {
        const msgId = hash.replace('#msg-', '');
        navigateToMessage(msgId);
    } else if (hash.startsWith('#topic-')) {
        const topicId = hash.replace('#topic-', '');
        navigateToTopic(topicId, false);
    } else {
        // Показываем первый топик по умолчанию
        const firstTab = document.querySelector('.tab');
        if (firstTab) {
            navigateToTopic(firstTab.dataset.id, false);
        }
    }
}

// Обработка начальной навигации
function handleInitialNavigation() {
    if (window.location.hash) {
        setTimeout(() => {
            handleNavigation();
        }, 100);
    } else {
        const firstTab = document.querySelector('.tab');
        if (firstTab) {
            navigateToTopic(firstTab.dataset.id, false);
        }
    }
}

// Навигация к сообщению
function navigateToMessage(msgId) {
    const messageInfo = findMessage(msgId);
    
    if (!messageInfo) {
        console.warn(`Сообщение с ID ${msgId} не найдено`);
        return;
    }
    
    const currentTopicId = getCurrentTopicId();
    const needTopicSwitch = currentTopicId !== messageInfo.topicId;
    
    if (needTopicSwitch) {
        // Переключаемся на нужный топик без прокрутки наверх
        navigateToTopic(messageInfo.topicId, false, false);
        
        // Ждем переключения топика
        setTimeout(() => {
            scrollToMessage(messageInfo.element);
        }, 300);
    } else {
        // Небольшая задержка для завершения рендеринга
        setTimeout(() => {
            scrollToMessage(messageInfo.element);
        }, 50);
    }
}

// Прокрутка к сообщению
function scrollToMessage(element) {
    // Ждем загрузки изображений в области
    waitForImages(element).then(() => {
        // Рассчитываем позицию
        const navHeight = 80;
        const viewportOffset = window.innerHeight * 0.1;
        const elementRect = element.getBoundingClientRect();
        const targetOffset = elementRect.top + window.pageYOffset - navHeight - viewportOffset;
        
        // Прокручиваем
        window.scrollTo({
            top: Math.max(0, targetOffset),
            behavior: 'smooth'
        });
        
        // Выделяем сообщение
        setTimeout(() => {
            highlightMessage(element);
        }, 300);
        
        // Корректируем позицию после загрузки контента
        setTimeout(() => {
            correctScrollPosition(element);
        }, 800);
    });
}

// Ожидание загрузки изображений
function waitForImages(element) {
    return new Promise((resolve) => {
        const container = element.closest('section') || document;
        const images = Array.from(container.querySelectorAll('img')).filter(img => {
            const imgRect = img.getBoundingClientRect();
            const elementRect = element.getBoundingClientRect();
            const distance = Math.abs(imgRect.top - elementRect.top);
            return distance < window.innerHeight * 2;
        });
        
        if (images.length === 0) {
            resolve();
            return;
        }
        
        let loadedCount = 0;
        const timeout = setTimeout(() => resolve(), 2000);
        
        const checkComplete = () => {
            loadedCount++;
            if (loadedCount >= images.length) {
                clearTimeout(timeout);
                resolve();
            }
        };
        
        images.forEach(img => {
            if (img.complete && img.naturalHeight !== 0) {
                checkComplete();
            } else {
                const handleLoad = () => {
                    img.removeEventListener('load', handleLoad);
                    img.removeEventListener('error', handleLoad);
                    checkComplete();
                };
                
                img.addEventListener('load', handleLoad);
                img.addEventListener('error', handleLoad);
            }
        });
    });
}

// Корректировка позиции прокрутки
function correctScrollPosition(element) {
    const rect = element.getBoundingClientRect();
    const navHeight = 80;
    const idealTop = navHeight + (window.innerHeight * 0.1);
    const tolerance = 50;
    
    if (Math.abs(rect.top - idealTop) > tolerance) {
        const correctedOffset = element.getBoundingClientRect().top + 
                              window.pageYOffset - navHeight - (window.innerHeight * 0.1);
        
        window.scrollTo({
            top: Math.max(0, correctedOffset),
            behavior: 'smooth'
        });
    }
}

// Выделение сообщения
function highlightMessage(element) {
    // Убираем предыдущие выделения
    document.querySelectorAll('.message-highlight').forEach(el => {
        el.classList.remove('message-highlight');
        el.style.boxShadow = '';
    });
    
    // Добавляем новое выделение
    element.classList.add('message-highlight');
    element.style.boxShadow = '0 0 0 2px #58a6ff';
    element.style.transition = 'box-shadow 0.3s ease';
    
    // Убираем выделение через 3 секунды
    setTimeout(() => {
        element.classList.remove('message-highlight');
        element.style.boxShadow = '';
    }, 3000);
}

// Получение ID текущего топика
function getCurrentTopicId() {
    const activeTab = document.querySelector('.tab.bg-github-hover');
    return activeTab ? activeTab.dataset.id : null;
}

// Поиск сообщения
function findMessage(msgId) {
    if (isIndexBuilt && messageIndex.has(msgId)) {
        return messageIndex.get(msgId);
    }
    
    // Fallback поиск
    const allSections = document.querySelectorAll('section[id^="topic-"]');
    for (const section of allSections) {
        const msgElement = section.querySelector(`#msg-${msgId}`);
        if (msgElement) {
            return {
                element: msgElement,
                topicId: section.id.replace('topic-', ''),
                section: section
            };
        }
    }
    return null;
}

// Настройка ленивой загрузки изображений
function setupLazyLoading() {
    if (!('IntersectionObserver' in window)) return;
    
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                observer.unobserve(img);
                
                if (!img.complete) {
                    img.style.opacity = '0';
                    img.style.transition = 'opacity 0.3s ease';
                    
                    const handleLoad = () => {
                        img.style.opacity = '1';
                        img.removeEventListener('load', handleLoad);
                        img.removeEventListener('error', handleLoad);
                    };
                    
                    img.addEventListener('load', handleLoad);
                    img.addEventListener('error', handleLoad);
                    
                    if (img.complete) {
                        handleLoad();
                    }
                }
            }
        });
    }, {
        rootMargin: '50px 0px',
        threshold: 0.1
    });
    
    document.querySelectorAll('img[loading="lazy"]').forEach(img => {
        if (!img.complete || img.naturalHeight === 0) {
            imageObserver.observe(img);
        }
    });
}

// Клавиатурная навигация
function setupKeyboardNavigation() {
    document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            const tabs = Array.from(document.querySelectorAll('.tab'));
            const activeTab = document.querySelector('.tab.bg-github-hover');
            
            if (activeTab) {
                const currentIndex = tabs.indexOf(activeTab);
                let newIndex;
                
                if (e.key === 'ArrowLeft') {
                    newIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
                } else {
                    newIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
                }
                
                navigateToTopic(tabs[newIndex].dataset.id);
            }
        }
    });
}

// Инициализация подсветки синтаксиса
function initializeCodeHighlighting() {
    if (typeof hljs === 'undefined') {
        console.warn('Highlight.js не загружен');
        return;
    }

    document.querySelectorAll('pre code').forEach(block => {
        enhanceCodeBlock(block);
    });
}

// Улучшение блока кода
function enhanceCodeBlock(codeElement) {
    const preElement = codeElement.parentElement;
    
    if (preElement.classList.contains('hljs-processed')) {
        return;
    }
    
    const codeText = codeElement.textContent || codeElement.innerText;
    const language = getLanguageFromClass(codeElement);
    
    // Применяем подсветку синтаксиса
    let highlightedCode;
    if (language && hljs.getLanguage(language)) {
        try {
            highlightedCode = hljs.highlight(codeText, { language }).value;
        } catch (e) {
            console.warn('Ошибка подсветки синтаксиса:', e);
            highlightedCode = hljs.highlightAuto(codeText).value;
        }
    } else {
        highlightedCode = hljs.highlightAuto(codeText).value;
    }
    
    // Создаем структуру с номерами строк
    const lines = codeText.split('\n');
    const lineNumbers = lines.map((_, index) => index + 1).join('\n');
    
    const wrapper = document.createElement('div');
    wrapper.className = 'code-block-with-lines';
    
    const newPre = document.createElement('pre');
    newPre.className = 'hljs-processed';
    
    const lineNumbersDiv = document.createElement('div');
    lineNumbersDiv.className = 'code-line-numbers';
    lineNumbersDiv.textContent = lineNumbers;
    
    const codeContentDiv = document.createElement('div');
    codeContentDiv.className = 'code-content';
    
    const newCode = document.createElement('code');
    newCode.className = language ? `language-${language}` : '';
    newCode.innerHTML = highlightedCode;
    
    codeContentDiv.appendChild(newCode);
    newPre.appendChild(lineNumbersDiv);
    newPre.appendChild(codeContentDiv);
    wrapper.appendChild(newPre);
    
    preElement.parentNode.replaceChild(wrapper, preElement);
}

// Извлечение языка из класса
function getLanguageFromClass(codeElement) {
    const classList = codeElement.classList;
    
    for (const className of classList) {
        if (className.startsWith('language-')) {
            return className.replace('language-', '');
        }
    }
    
    return null;
}
