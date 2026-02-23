async function run() {
    let browser;
    let timeout;
    
    try {
        browser = await chromium.launch({ 
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        
        const page = await browser.newPage();
        
        timeout = setTimeout(async () => {
            if (browser) await browser.close();
        }, 240000); // 4 минуты
        
        await page.goto(URL);
        
        // Поиск стола (как обычно)
        let activeLink = null;
        let attempts = 0;
        while (!activeLink && attempts < 10) {
            activeLink = await findLastLiveGame(page);
            if (!activeLink) {
                await page.waitForTimeout(5000);
                attempts++;
            }
        }
        
        if (!activeLink) return;
        
        await page.click(`a[href="${activeLink}"]`);
        
        // ===== НОВАЯ ЛОГИКА =====
        let gameNumber = getGameNumberByTime();
        if (!gameNumber) return;
        
        let cards = { player: [], banker: [], pScore: '0', bScore: '0' };
        let gameOverDetected = false;
        
        // Запускаем одновременное наблюдение
        while (!gameOverDetected) {
            // Читаем карты каждые 100мс
            cards = await getCards(page);
            
            // Проверяем, не завершилась ли игра
            gameOverDetected = await page.evaluate(() => {
                return document.querySelector('.market-grid__game-over-panel') !== null;
            }).catch(() => false);
            
            if (gameOverDetected) break;
            await page.waitForTimeout(100);
        }
        
        // Игра завершена - отправляем последние прочитанные карты
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
        
        await page.waitForTimeout(10000);
        
    } catch (e) {
        console.log('Ошибка:', e.message);
    } finally {
        if (timeout) clearTimeout(timeout);
        if (browser) await browser.close();
    }
}