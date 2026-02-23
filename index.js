const { chromium } = require('playwright');
const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');

const TOKEN = '8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU';
const CHAT = '-1003179573402';
const URL = 'https://1xlite-7636770.bar/ru/live/baccarat';
const LAST_NUMBER_FILE = './last_number.txt';

const bot = new TelegramBot(TOKEN, { polling: false });

let lastMessageId = null;
let lastMessageText = '';
let lastGameNumber = '0';

if (fs.existsSync(LAST_NUMBER_FILE)) {
    lastGameNumber = fs.readFileSync(LAST_NUMBER_FILE, 'utf8');
    console.log('Загружен последний номер:', lastGameNumber);
}

function formatCards(cards) {
    return cards.join('');
}

function determineTurn(playerCards, bankerCards) {
    if (playerCards.length === 2 && bankerCards.length === 2) return 'player';
    if (playerCards.length === 3 && bankerCards.length === 2) return 'banker';
    if (playerCards.length === 2 && bankerCards.length === 3) return 'player';
    return null;
}

function getGameNumberByTime() {
    const now = new Date();
    const mskTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Moscow' }));
    
    const currentHours = mskTime.getHours();
    const currentMinutes = mskTime.getMinutes();
    const currentSeconds = mskTime.getSeconds();
    
    const startHour = 3;
    const startMinute = 0;
    
    if (currentHours < startHour || (currentHours === startHour && currentMinutes < startMinute)) {
        return null;
    }
    
    let minutesSinceStart = (currentHours - startHour) * 60 + (currentMinutes - startMinute);
    
    if (currentSeconds < 5) {
        minutesSinceStart -= 1;
    }
    
    return minutesSinceStart + 1;
}

async function sendOrEditTelegram(newMessage) {
    if (!newMessage || newMessage === lastMessageText) return;
    
    try {
        if (lastMessageId) {
            await bot.editMessageText(newMessage, {
                chat_id: CHAT,
                message_id: lastMessageId
            });
        } else {
            const msg = await bot.sendMessage(CHAT, newMessage);
            lastMessageId = msg.message_id;
        }
        lastMessageText = newMessage;
    } catch (e) {
        console.log('TG error:', e.message);
    }
}

// ===== ПОИСК НИЖНЕГО СТОЛА =====
async function findLastLiveGame(page) {
    const games = await page.$$('.dashboard-game');
    console.log(`Найдено столов: ${games.length}`);
    
    // Проходим с конца, чтобы найти последний активный стол
    for (let i = games.length - 1; i >= 0; i--) {
        const game = games[i];
        
        const hasTimer = await game.$('.dashboard-game-info__time') !== null;
        if (!hasTimer) continue;

        const isFinished = await game.evaluate(el => {
            const period = el.querySelector('.dashboard-game-info__period');
            return period?.textContent.includes('Игра завершена') ?? false;
        });

        if (!isFinished) {
            const link = await game.$('a[href*="/ru/live/baccarat/"]');
            if (link) {
                const href = await link.getAttribute('href');
                console.log(`🎯 Найден нижний активный стол (позиция ${i+1} из ${games.length})`);
                return href;
            }
        }
    }
    
    console.log('❌ Активных столов не найдено');
    return null;
}

async function getCards(page) {
    const playerBlock = await page.$('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__cards');
    const player = playerBlock ? await playerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }) : [];

    const bankerBlock = await page.$('.baccarat-player--is-reversed .baccarat-player__cards');
    const banker = bankerBlock ? await bankerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }) : [];

    const pScore = await page.$eval('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__number', el => el.textContent).catch(() => '0');
    const bScore = await page.$eval('.baccarat-player--is-reversed .baccarat-player__number', el => el.textContent).catch(() => '0');

    return { player, banker, pScore, bScore };
}

async function monitorGame(page, gameNumber) {
    let lastCards = { player: [], banker: [], pScore: '0', bScore: '0' };
    
    while (true) {
        // Проверяем, не закрыта ли страница
        if (page.isClosed()) {
            console.log('⚠️ Страница закрыта, выходим из мониторинга');
            break;
        }
        
        const cards = await getCards(page);
        
        const isGameOver = await page.evaluate(() => {
            const panel = document.querySelector('.market-grid__game-over-panel');
            if (!panel) return false;
            const caption = panel.querySelector('.ui-caption');
            return caption && caption.textContent.includes('Игра завершена');
        }).catch(() => false);
        
        if (isGameOver) {
            const cards = await getCards(page).catch(() => ({ player: [], banker: [], pScore: '0', bScore: '0' }));
            
            if (cards.player.length > 0 || cards.banker.length > 0) {
                const total = parseInt(cards.pScore) + parseInt(cards.bScore);
                const winner = cards.pScore > cards.bScore ? 'П1' : (cards.bScore > cards.pScore ? 'П2' : 'X');
                const noDrawFlag = cards.player.length === 2 && cards.banker.length === 2 ? '#R ' : '';
                
                let message;
                if (cards.pScore > cards.bScore) {
                    message = `#N${gameNumber} ✅${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                } else if (cards.bScore > cards.pScore) {
                    message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ✅${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                } else {
                    message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) 🔰 ${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                }
                
                await sendOrEditTelegram(message);
            }
            
            try {
                await page.waitForTimeout(10000);
            } catch (e) {
                console.log('⚠️ Страница закрыта во время ожидания');
            }
            break;
        }
        
        if (cards.player.length > 0 && cards.banker.length > 0) {
            const turn = determineTurn(cards.player, cards.banker);
            
            let message;
            if (turn === 'player') {
                message = `⏱№${gameNumber} 👉${cards.pScore}(${formatCards(cards.player)}) -${cards.bScore} (${formatCards(cards.banker)})`;
            } else if (turn === 'banker') {
                message = `⏱№${gameNumber} ${cards.pScore}(${formatCards(cards.player)}) -👉${cards.bScore} (${formatCards(cards.banker)})`;
            } else {
                message = `⏱№${gameNumber} ${cards.pScore}(${formatCards(cards.player)}) -${cards.bScore} (${formatCards(cards.banker)})`;
            }
            
            const cardsChanged = 
                JSON.stringify(cards.player) !== JSON.stringify(lastCards.player) ||
                JSON.stringify(cards.banker) !== JSON.stringify(lastCards.banker) ||
                cards.pScore !== lastCards.pScore ||
                cards.bScore !== lastCards.bScore;
            
            if (cardsChanged) {
                await sendOrEditTelegram(message);
                lastCards = { ...cards };
            }
        }
        
        try {
            await page.waitForTimeout(2000);
        } catch (e) {
            console.log('⚠️ Страница закрыта, выходим');
            break;
        }
    }
}

// ===== ОСНОВНАЯ ФУНКЦИЯ =====
async function run() {
    let browser;
    let timeout;
    const startTime = Date.now();
    
    try {
        console.log(`\n🟢 Браузер открыт в ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}`);
        
        browser = await chromium.launch({ 
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        
        const page = await browser.newPage();
        
        // Жизнь браузера 4 минуты (240 секунд)
        timeout = setTimeout(async () => {
            console.log(`⏱ 4 минуты прошло, закрываю браузер`);
            if (browser && browser.isConnected()) {
                await browser.close().catch(() => {});
            }
        }, 240000);
        
        await page.goto(URL, { timeout: 30000 }).catch(e => {
            console.log('❌ Ошибка загрузки страницы:', e.message);
            return;
        });
        
        // Ищем нижний активный стол
        let activeLink = null;
        let attempts = 0;
        while (!activeLink && attempts < 10) {
            if (page.isClosed()) break;
            activeLink = await findLastLiveGame(page).catch(() => null);
            if (!activeLink) {
                console.log('Жду 5 секунд...');
                await page.waitForTimeout(5000).catch(() => {});
                attempts++;
            }
        }
        
        if (!activeLink || page.isClosed()) {
            console.log('❌ Не нашел активный стол за 10 попыток');
            return;
        }
        
        console.log('Захожу в нижний стол:', activeLink);
        await page.click(`a[href="${activeLink}"]`).catch(() => {});
        
        // Ждем либо карты, либо завершение
        await Promise.race([
            page.waitForSelector('.baccarat-player__cards', { timeout: 5000 }).catch(() => {}),
            page.waitForSelector('.market-grid__game-over-panel', { timeout: 5000 }).catch(() => {})
        ]).catch(() => {});
        
        if (page.isClosed()) return;
        
        let gameNumber = getGameNumberByTime();
        if (!gameNumber) {
            console.log('⏰ До начала игр еще время (старт в 3:00 МСК)');
            return;
        }
        
        gameNumber = gameNumber.toString();
        console.log('🎰 Номер игры по времени (МСК):', gameNumber);
        
        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);
        
        // Сразу читаем карты
        let initialCards = await getCards(page).catch(() => ({ player: [], banker: [], pScore: '0', bScore: '0' }));
        console.log(`📊 Начальные карты: игрок ${initialCards.pScore} (${initialCards.player.length} карт), дилер ${initialCards.bScore} (${initialCards.banker.length} карт)`);
        
        // Проверяем, не завершилась ли игра
        const gameOverNow = await page.evaluate(() => {
            return document.querySelector('.market-grid__game-over-panel') !== null;
        }).catch(() => false);

        if (gameOverNow && (initialCards.player.length > 0 || initialCards.banker.length > 0)) {
            console.log('⚡ Игра-раздача! Отправляем сразу...');
            const total = parseInt(initialCards.pScore) + parseInt(initialCards.bScore);
            const winner = initialCards.pScore > initialCards.bScore ? 'П1' : (initialCards.bScore > initialCards.pScore ? 'П2' : 'X');
            const noDrawFlag = initialCards.player.length === 2 && initialCards.banker.length === 2 ? '#R ' : '';
            
            let message;
            if (initialCards.pScore > initialCards.bScore) {
                message = `#N${gameNumber} ✅${initialCards.pScore} (${formatCards(initialCards.player)}) - ${initialCards.bScore} (${formatCards(initialCards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            } else if (initialCards.bScore > initialCards.pScore) {
                message = `#N${gameNumber} ${initialCards.pScore} (${formatCards(initialCards.player)}) - ✅${initialCards.bScore} (${formatCards(initialCards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            } else {
                message = `#N${gameNumber} ${initialCards.pScore} (${formatCards(initialCards.player)}) 🔰 ${initialCards.bScore} (${formatCards(initialCards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
            }
            
            await sendOrEditTelegram(message);
            await page.waitForTimeout(10000).catch(() => {});
            return;
        }
        
        // Если не раздача — начинаем мониторинг
        console.log('🎮 Начинаю мониторинг игры...');
        await monitorGame(page, gameNumber);
        
    } catch (e) {
        console.log('❌ Ошибка:', e.message);
    } finally {
        if (timeout) clearTimeout(timeout);
        if (browser && browser.isConnected()) {
            await browser.close().catch(() => {});
            console.log(`🔴 Браузер закрыт в ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}, прожил ${(Date.now() - startTime)/1000} сек`);
            lastMessageId = null;
            lastMessageText = '';
        }
    }
}

// ===== ЗАДЕРЖКА ДО :58 =====
function getDelayTo58() {
    const now = new Date();
    const seconds = now.getSeconds();
    const milliseconds = now.getMilliseconds();
    const targetSeconds = 58;
    
    let delaySeconds;
    if (seconds < targetSeconds) {
        delaySeconds = targetSeconds - seconds;
    } else {
        delaySeconds = (60 - seconds) + targetSeconds;
    }
    
    return (delaySeconds * 1000) - milliseconds;
}

// ===== ЗАПУСК =====
(async () => {
    console.log('🤖 Бот Baccarat запущен');
    console.log('🎯 Номера по московскому времени (3:00 = #1)');
    console.log('🎯 Захожу в НИЖНИЙ активный стол');
    console.log('⏱ Запуск в :58 каждой минуты');
    console.log('⏱ Жизнь браузера: 4 минуты (240 секунд)');
    
    const initialDelay = getDelayTo58();
    const nextRunTime = new Date(Date.now() + initialDelay);
    console.log(`⏱ Первый запуск через ${(initialDelay/1000).toFixed(3)} секунд`);
    console.log(`⏱ Время первого запуска: ${nextRunTime.toLocaleTimeString()}.${nextRunTime.getMilliseconds()}`);
    
    await new Promise(resolve => setTimeout(resolve, initialDelay));
    console.log('✅ Синхронизировались!');
    
    while (true) {
        const now = new Date();
        console.log(`\n🚀 Запуск браузера в ${now.toLocaleTimeString()}.${now.getMilliseconds()}`);
        
        run();
        
        // Ждем ровно 60 секунд до следующего :58
        await new Promise(resolve => setTimeout(resolve, 60000));
    }
})();